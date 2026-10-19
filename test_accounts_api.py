"""End-to-end API boundaries for persistent accounts, without an Android adapter."""
import hashlib
import hmac
import secrets
import sqlite3
import time
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from account_ledger import AccountLedger
from accounts import AccountStore
from servertec import Database, FirebaseVerifier, HOUR_MS, Settings, create_app


PASSWORD = "a long private test passphrase"
NEW_PASSWORD = "another long private test passphrase"


class FastTestHasher:
    """Only a fixture: crypto behavior is exercised by real-scrypt and TLS tests."""
    dummy_hash = "test-only:" + "0" * 64

    def hash(self, password):
        return "test-only:" + hashlib.sha256(password.encode()).hexdigest()

    def verify(self, password, encoded):
        return hmac.compare_digest(self.hash(password), encoded)


class Harness:
    def __init__(self, root, *, legacy=False, testing=False):
        self.sessions = {}
        self.now = [int(time.time() * 1000)]
        self.db = Database(root / "runtime" / "servertec.db", clock=lambda: self.now[0])
        if legacy:
            self.db.hearts_for_device("legacy-google", "a" * 64, "programming", str(uuid4()))
            self.db.complete("legacy-google", "lesson", "math_2", "lesson_1")
        self.ledger = AccountLedger(self.db)
        self.settings = Settings(root / "runtime", testing=testing, project_id="test-project",
            testing_token_hash=hashlib.sha256(b"isolated-test-token").hexdigest())
        self.store = AccountStore(self.db, self.ledger.enroll, hasher=FastTestHasher(),
                                 firebase_project="" if testing else "test-project")
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.verifier = FirebaseVerifier("test-project")
        self.verifier.keys = {"test-signing-key": self.key.public_key()}
        self.verifier.expires = time.monotonic() + 3600

    def client(self):
        app = create_app(self.settings, self.db, verifier=self.verifier, accounts=self.store)
        client = TestClient(app, base_url="https://127.0.0.1", client=("127.0.0.1", 55000))
        client.headers["X-Android-Id"] = "0123456789abcdef"
        return client

    def invitation(self):
        return self.store.issue_invitation()["invitation"]

    def register(self, client, username="Aresitos56"):
        response = client.post("/v2/auth/register", json={
            "username": username, "password": PASSWORD, "invitation": self.invitation()})
        assert response.status_code == 201, response.text
        result = response.json()
        self.link(client, result)
        return result

    def link(self, client, result, device="0123456789abcdef"):
        self.sessions[result["account_id"]] = result["access_token"]
        headers = {**self.bearer(result), "X-Android-Id": device}
        pending = client.post("/v2/devices/prepare", headers=headers)
        assert pending.status_code == 200
        if pending.json()["status"] == "confirmation_required":
            confirmed = client.post("/v2/devices/confirm", headers=headers, json={
                "confirmation_token": pending.json()["confirmation_token"]})
            assert confirmed.status_code == 200

    def jwt(self, subject="new-google", **changes):
        now = int(time.time())
        claims = {"sub": subject, "iss": "https://securetoken.google.com/test-project",
                  "aud": "test-project", "iat": now, "exp": now + 3600,
                  "auth_time": now, "firebase": {"sign_in_provider": "google.com"}}
        claims.update(changes)
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "test-signing-key"})

    def debit_internal(self, account_id, route="programming"):
        # Only the internal transaction primitive; no public debit API is added.
        con = self.db.connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            con.row_factory = sqlite3.Row
            groups = self.store.on_enroll.__self__
            result = groups.debit_in_transaction(con, self.sessions[account_id],
                                                 "0123456789abcdef", route)
            con.commit()
            return result
        finally:
            con.close()

    @staticmethod
    def bearer(result):
        return {"Authorization": "Bearer " + result["access_token"]}


@pytest.fixture
def api(tmp_path):
    return Harness(tmp_path)


def test_recreated_client_server_and_device_headers_keep_the_same_balance(api):
    with api.client() as client:
        registered = api.register(client)
        assert api.debit_internal(registered["account_id"])["available"] == 7
        assert client.get("/v2/hearts/programming", headers=api.bearer(registered)).json()["available"] == 7
    api.store = AccountStore(api.db, api.ledger.enroll, hasher=FastTestHasher(),
                             firebase_project="test-project")
    with api.client() as client:
        login = client.post("/v2/auth/login", json={"username": "aresitos56", "password": PASSWORD})
        assert login.status_code == 200
        result = login.json()
        assert result["account_id"] == registered["account_id"]
        for device in ("0123456789abcdef", "ffffffffffffffff"):
            headers = {**api.bearer(result), "X-Android-Id": device,
                       "X-User-Id": "a-different-account", "X-Forwarded-For": "203.0.113.23"}
            if device != "0123456789abcdef":
                assert client.get("/v2/hearts/programming", headers=headers).status_code == 409
            api.link(client, result, device)
            response = client.get("/v2/hearts/programming", headers=headers)
            assert response.json()["available"] == 7
            assert response.headers["cache-control"] == "no-store"
        assert client.get("/v2/hearts/programming", headers={
            **api.bearer(result), "X-Android-Id": "client-invented-id"}).status_code == 422
        assert client.get("/v2/auth/me", headers=api.bearer(result)).json() == {
            "account_id": result["account_id"]}
        assert client.get("/v2/hearts/math_physics", headers=api.bearer(result)).json()["available"] == 12
        assert client.get("/v2/hearts/programming").status_code == 401


def test_invitation_is_required_consumed_once_and_usernames_are_case_insensitive(api):
    invitation = api.invitation()
    with api.client() as client:
        body = {"username": "Aresitos56", "password": PASSWORD, "invitation": invitation}
        assert client.post("/v2/auth/register", json=body).status_code == 201
        assert client.post("/v2/auth/register", json={**body, "username": "AnotherUser"}).status_code == 403
        assert client.post("/v2/auth/register", json={
            **body, "username": "aresitos56", "invitation": api.invitation()}).status_code == 409
        assert client.post("/v2/auth/register", json={
            "username": "NoInvite", "password": PASSWORD}).status_code == 422


@pytest.mark.parametrize("extra", [
    {"uid": "someone-else"}, {"account_id": "chosen-by-phone"},
    {"role": "admin"}, {"premium": True}, {"balance": 999},
])
def test_client_cannot_choose_identity_privileges_or_balance(api, extra):
    with api.client() as client:
        body = {"username": "Aresitos56", "password": PASSWORD,
                "invitation": api.invitation(), **extra}
        response = client.post("/v2/auth/register", json=body)
        assert response.status_code == 422
        assert response.json() == {"error": "invalid_request"}
        assert PASSWORD not in response.text


def test_missing_wallet_fails_closed_without_new_grant(api):
    with api.client() as client:
        registered = api.register(client)
        api.debit_internal(registered["account_id"])
        con = api.db.connect()
        try:
            con.execute("DELETE FROM group_hearts WHERE group_id IN "
                        "(SELECT group_id FROM group_accounts WHERE account_id=?) AND route='programming'",
                        (registered["account_id"],))
        finally:
            con.close()
        response = client.get("/v2/hearts/programming", headers=api.bearer(registered))
        assert response.status_code == 503
        assert response.json() == {"error": "wallet_state_missing"}
        login = client.post("/v2/auth/login", json={"username": "aresitos56", "password": PASSWORD}).json()
        assert login["account_id"] == registered["account_id"]
        assert client.get("/v2/hearts/programming", headers=api.bearer(login)).status_code == 503


def test_password_recovery_logout_and_session_rotation_preserve_wallet(api):
    with api.client() as client:
        registered = api.register(client)
        api.debit_internal(registered["account_id"])
        recovered = client.post("/v2/auth/recover", json={
            "username": "ARESITOS56", "recovery_code": registered["recovery_code"],
            "new_password": NEW_PASSWORD})
        assert recovered.status_code == 200
        assert recovered.json()["require_login"]
        assert "access_token" not in recovered.json()
        assert client.get("/v2/auth/me", headers=api.bearer(registered)).status_code == 401
        assert client.post("/v2/auth/login", json={"username": "aresitos56", "password": PASSWORD}).status_code == 401
        login = client.post("/v2/auth/login", json={
            "username": "Aresitos56", "password": NEW_PASSWORD}).json()
        assert login["account_id"] == registered["account_id"]
        assert client.get("/v2/hearts/programming", headers=api.bearer(login)).json()["available"] == 7
        assert client.post("/v2/auth/recover", json={
            "username": "Aresitos56", "recovery_code": registered["recovery_code"],
            "new_password": PASSWORD}).status_code == 401
        changed = client.post("/v2/auth/password", headers=api.bearer(login), json={
            "current_password": NEW_PASSWORD, "new_password": PASSWORD})
        assert changed.status_code == 200
        assert client.get("/v2/auth/me", headers=api.bearer(login)).status_code == 401
        assert client.post("/v2/auth/logout", headers=api.bearer(changed.json())).status_code == 200
        assert client.get("/v2/auth/me", headers=api.bearer(changed.json())).status_code == 401


def test_failed_storage_never_reports_registration_or_consumes_invitation(api):
    invitation = api.invitation()
    original = api.store.on_enroll

    def broken_enrollment(*args):
        raise sqlite3.OperationalError("private-storage-diagnostic")

    api.store.on_enroll = broken_enrollment
    with api.client() as client:
        body = {"username": "Aresitos56", "password": PASSWORD, "invitation": invitation}
        response = client.post("/v2/auth/register", json=body)
        assert response.status_code == 503
        assert response.json() == {"error": "storage_unavailable"}
        api.store.on_enroll.__self__.prior_enroll = original
        assert client.post("/v2/auth/register", json=body).status_code == 201


def test_login_limits_survive_reopen_and_ignore_forwarded_ip(api):
    with api.client() as client:
        api.register(client)
        for attempt in range(10):
            response = client.post("/v2/auth/login",
                headers={"X-Forwarded-For": "203.0.113." + str(attempt)},
                json={"username": "ARESITOS56" if attempt % 2 else "aresitos56",
                      "password": "incorrect but long enough"})
            assert response.status_code == 401
    api.store = AccountStore(api.db, api.ledger.enroll, hasher=FastTestHasher(),
                             firebase_project="test-project")
    with api.client() as client:
        response = client.post("/v2/auth/login", json={"username": "Aresitos56", "password": PASSWORD})
        assert response.status_code == 429
        assert int(response.headers["retry-after"]) > 0


def test_disabled_account_cannot_use_new_or_old_production_routes(api):
    with api.client() as client:
        registered = api.register(client)
        api.store.disable_account(registered["account_id"])
        assert client.get("/v2/auth/me", headers=api.bearer(registered)).status_code == 401
        for path in ("/v1/hearts/programming", "/v1/progress", "/v1/settings"):
            response = client.get(path, headers={"Authorization": "Bearer " + api.jwt()})
            assert response.status_code == 410
        assert client.put("/v1/progress/completions", json={
            "kind": "lesson", "course": "math_2", "item": "lesson_2"}).status_code == 410
        assert client.post("/v1/hearts/debits", json={
            "operation_id": str(uuid4()), "route": "programming"}).status_code == 410
        assert client.post("/v2/hearts/debits", headers=api.bearer(registered), json={
            "operation_id": str(uuid4()), "route": "programming"}).status_code in (404, 405)


def test_google_new_account_requires_invite_and_sessions_do_not_outlive_id_token(api):
    token = api.jwt(exp=int(time.time()) + 120)
    with api.client() as client:
        assert client.post("/v2/auth/google", json={"id_token": token}).status_code == 403
        result = client.post("/v2/auth/google", json={
            "id_token": token, "invitation": api.invitation()})
        assert result.status_code == 200
        first = result.json()
        api.link(client, first)
        assert first["expires_at_ms"] <= (int(time.time()) + 120) * 1000
        api.debit_internal(first["account_id"])
        second = client.post("/v2/auth/google", json={"id_token": token}).json()
        assert second["account_id"] == first["account_id"]
        assert client.get("/v2/hearts/programming", headers=api.bearer(second)).json()["available"] == 7
        assert first["access_token"] != second["access_token"]


def test_google_legacy_identity_migrates_once_and_keeps_progress(tmp_path):
    api = Harness(tmp_path, legacy=True)
    with api.client() as client:
        first = client.post("/v2/auth/google", json={"id_token": api.jwt("legacy-google")})
        assert first.status_code == 200
        identity = first.json()
        api.link(client, identity)
        assert client.get("/v2/hearts/programming", headers=api.bearer(identity)).json()["available"] == 7
        assert client.get("/v2/progress", headers=api.bearer(identity)).json()["completed"][0]["item"] == "lesson_1"
        api.debit_internal(identity["account_id"])
        again = client.post("/v2/auth/google", json={"id_token": api.jwt("legacy-google")}).json()
        assert again["account_id"] == identity["account_id"]
        assert client.get("/v2/hearts/programming", headers=api.bearer(again)).json()["available"] == 6


@pytest.mark.parametrize("claims", [
    {"aud": "other-project"},
    {"iss": "https://securetoken.google.com/other-project"},
    {"firebase": {"sign_in_provider": "anonymous"}},
    {"exp": int(time.time()) - 1},
    {"auth_time": True},
])
def test_google_invalid_issuer_provider_or_dates_rejected(api, claims):
    with api.client() as client:
        response = client.post("/v2/auth/google", json={
            "id_token": api.jwt(**claims), "invitation": api.invitation()})
        assert response.status_code == 401
        assert "access_token" not in response.json()


def test_testing_credential_does_not_impersonate_a_v2_account(tmp_path):
    api = Harness(tmp_path, testing=True)
    with api.client() as client:
        headers = {"Authorization": "Bearer isolated-test-token"}
        assert client.get("/v1/hearts/programming", headers=headers).status_code == 200
        assert client.get("/v2/hearts/programming", headers=headers).status_code == 401
        assert client.post("/v2/auth/google", json={"id_token": api.jwt()}).status_code == 403


def test_auth_body_and_transport_errors_do_not_echo_secrets(api):
    with api.client() as client:
        response = client.post("/v2/auth/login", json={"username": "Aresitos56", "password": "S" * 20_000})
        assert response.status_code == 413
        assert "S" * 50 not in response.text
        response = client.post("/v2/auth/login", json={"username": 123, "password": PASSWORD})
        assert response.status_code == 422
        assert PASSWORD not in response.text
        response = client.post("http://127.0.0.1/v2/auth/login", json={
            "username": "Aresitos56", "password": PASSWORD})
        assert response.status_code == 400
