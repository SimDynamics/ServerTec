import hashlib
import hmac
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest

import accounts
from accounts import AccountError, AccountStore, DAY_MS, GOOGLE_SESSION_MS, LOCAL_SESSION_MS, ScryptHasher
from servertec import Database


PASSWORD = "A complete pass phrase 123"
NEW_PASSWORD = "A different pass phrase 456"
PEER = "127.0.0.1"


class FastHasher:
    """Only for state-machine tests; production uses ScryptHasher unconditionally."""
    dummy_hash = hashlib.sha256(b"a nonexistent account password").hexdigest()

    def __init__(self):
        self.calls = []

    def hash(self, password):
        self.calls.append(("hash", None))
        return hashlib.sha256(password.encode()).hexdigest()

    def verify(self, password, encoded):
        self.calls.append(("verify", encoded))
        return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), encoded)


@pytest.fixture
def db(tmp_path):
    clock = [1_800_000_000_000]
    database = Database(tmp_path / "runtime" / "auth.db", clock=lambda: clock[0])
    return database, clock


@pytest.fixture
def store(db):
    return AccountStore(db[0], hasher=FastHasher(), firebase_project="test-project")


def register(store, username="Aresitos56", password=PASSWORD, peer=PEER):
    invite = store.issue_invitation()["invitation"]
    return store.register(username, password, invite, peer)


def assert_error(code, fn, status=None):
    with pytest.raises(AccountError) as caught:
        fn()
    assert caught.value.code == code
    if status is not None:
        assert caught.value.status == status
    return caught.value


def row_count(database, table):
    con = database.connect()
    try:
        return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        con.close()


def test_registration_case_insensitive_login_restart_and_private_storage(store, db):
    result = register(store)
    assert result["username"] == "Aresitos56"
    assert result["account_id"].startswith("acct_")
    assert result["account_id"] != "Aresitos56"
    assert result["expires_at_ms"] == db[1][0] + LOCAL_SESSION_MS
    assert store.authenticate(result["access_token"]) == result["account_id"]
    restarted = AccountStore(db[0], hasher=FastHasher(), firebase_project="test-project")
    login = restarted.login("aRESITOS56", PASSWORD, PEER)
    assert login["account_id"] == result["account_id"]
    assert "recovery_code" not in login
    assert login["access_token"] != result["access_token"]
    con = db[0].connect()
    try:
        dumped = "\n".join(con.iterdump())
        for secret in (PASSWORD, result["access_token"], result["recovery_code"]):
            assert secret not in dumped
        assert con.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        con.close()


@pytest.mark.parametrize("name", [" abcd", "abcd ", "ab", "a" * 33, "áresitos", "Ａresitos", "hello.world", "name\n", "a/b", "a\\b", "中文名字", None])
def test_username_validation_has_no_trimming_or_unicode_aliases(store, name):
    invitation = store.issue_invitation()["invitation"]
    assert_error("invalid_username", lambda: store.register(name, PASSWORD, invitation, PEER), 422)
    assert not store.hasher.calls


@pytest.mark.parametrize("password", ["a" * 14, "a" * 129, "\ud800" * 15, "", None])
def test_password_policy_rejects_invalid_input_before_hash(store, password):
    invite = store.issue_invitation()["invitation"]
    assert_error("invalid_password", lambda: store.register("Aresitos56", password, invite, PEER), 422)
    assert not store.hasher.calls


def test_passwords_preserve_whitespace_and_unicode_exactly(store):
    password = "  éducation très précise  "
    result = register(store, password=password)
    assert store.login("Aresitos56", password, PEER)["account_id"] == result["account_id"]
    assert_error("invalid_credentials", lambda: store.login("Aresitos56", password.strip(), PEER), 401)
    assert_error("invalid_credentials", lambda: store.login("Aresitos56", password.replace("é", "e\u0301"), PEER), 401)


def test_invalid_expired_and_consumed_invitations_cannot_create_accounts(store, db):
    assert_error("invalid_invitation", lambda: store.register("Aresitos56", PASSWORD, "guessed", PEER), 403)
    assert not store.hasher.calls
    invitation = store.issue_invitation(expires_in_ms=60_000)["invitation"]
    db[1][0] += 60_000
    assert_error("invalid_invitation", lambda: store.register("Aresitos56", PASSWORD, invitation, PEER), 403)
    invitation = store.issue_invitation()["invitation"]
    store.register("Aresitos56", PASSWORD, invitation, PEER)
    assert_error("invalid_invitation", lambda: store.register("Another56", PASSWORD, invitation, PEER), 403)
    assert row_count(db[0], "auth_accounts") == 1
    con = db[0].connect()
    try:
        assert invitation not in "\n".join(con.iterdump())
    finally:
        con.close()


def test_duplicate_name_does_not_consume_the_other_invitation(store):
    result = register(store)
    invitation = store.issue_invitation()["invitation"]
    assert_error("username_unavailable", lambda: store.register("aresitos56", PASSWORD, invitation, PEER), 409)
    another = store.register("AnotherUser", PASSWORD, invitation, PEER)
    assert another["account_id"] != result["account_id"]


def test_invitation_expiring_while_waiting_for_sqlite_writer_is_rejected(store, db, monkeypatch):
    invitation = store.issue_invitation(expires_in_ms=60_000)["invitation"]
    ready, proceed, entering_commit = threading.Event(), threading.Event(), threading.Event()
    original_recovery, original_transaction = store._new_recovery, store._transaction
    transactions = [0]
    def pause_before_transaction():
        result = original_recovery()
        ready.set()
        assert proceed.wait(5)
        return result
    @contextmanager
    def observe_transaction():
        transactions[0] += 1
        if transactions[0] == 2:  # rate-limit transaction is first
            entering_commit.set()
        with original_transaction() as con:
            yield con
    monkeypatch.setattr(store, "_new_recovery", pause_before_transaction)
    monkeypatch.setattr(store, "_transaction", observe_transaction)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(store.register, "Aresitos56", PASSWORD, invitation, PEER)
        assert ready.wait(5)
        holder = db[0].connect()
        try:
            holder.execute("BEGIN IMMEDIATE")
            proceed.set()
            assert entering_commit.wait(5)
            db[1][0] += 60_000
            holder.commit()
        finally:
            proceed.set()
            holder.close()
        assert_error("invalid_invitation", future.result, 403)
    assert row_count(db[0], "auth_accounts") == row_count(db[0], "auth_sessions") == 0


def test_enrollment_callback_account_invite_and_session_are_atomic(db):
    def fail(con, account_id, legacy_uid, now):
        assert con.in_transaction
        assert legacy_uid is None
        con.execute("INSERT INTO completions VALUES(?,?,?,?,?)", (account_id, "lesson", "course", "first", now))
        raise RuntimeError("intentional enrollment failure")
    store = AccountStore(db[0], on_enroll=fail, hasher=FastHasher())
    invitation = store.issue_invitation()["invitation"]
    with pytest.raises(RuntimeError, match="enrollment failure"):
        store.register("Aresitos56", PASSWORD, invitation, PEER)
    for table in ("auth_accounts", "auth_sessions", "completions"):
        assert row_count(db[0], table) == 0
    store.on_enroll = None
    assert store.register("Aresitos56", PASSWORD, invitation, PEER)["account_id"]


def test_concurrent_case_variant_registration_is_unique(store, db, monkeypatch):
    invitations = [store.issue_invitation()["invitation"] for _ in range(2)]
    barrier = threading.Barrier(2)
    original = store._new_account_id
    def synchronized_id():
        value = original()
        barrier.wait(timeout=5)
        return value
    monkeypatch.setattr(store, "_new_account_id", synchronized_id)
    def attempt(index):
        try:
            return store.register(["Aresitos56", "ARESITOS56"][index], PASSWORD,
                                  invitations[index], f"127.0.0.{index + 1}")
        except AccountError as error:
            return error
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert [result.code for result in results if isinstance(result, AccountError)] == ["username_unavailable"]
    assert row_count(db[0], "auth_accounts") == 1
    con = db[0].connect()
    try:
        assert con.execute("SELECT COUNT(*) FROM auth_invitations WHERE consumed_by IS NULL").fetchone()[0] == 1
    finally:
        con.close()


def test_concurrent_invitation_replay_creates_one_account(store, db, monkeypatch):
    invitation = store.issue_invitation()["invitation"]
    barrier = threading.Barrier(2)
    original = store._new_account_id
    def synchronized_id():
        value = original()
        barrier.wait(timeout=5)
        return value
    monkeypatch.setattr(store, "_new_account_id", synchronized_id)
    def attempt(index):
        try:
            return store.register(f"Aresitos{index}", PASSWORD, invitation, f"127.0.0.{index + 1}")
        except AccountError as error:
            return error
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert [result.code for result in results if isinstance(result, AccountError)] == ["invalid_invitation"]
    assert row_count(db[0], "auth_accounts") == row_count(db[0], "auth_sessions") == 1


def test_nonexistent_incorrect_disabled_login_return_generic_error_with_kdf(store):
    result = register(store)
    store.hasher.calls.clear()
    for username, password in (("MissingUser", PASSWORD), ("Aresitos56", NEW_PASSWORD)):
        assert_error("invalid_credentials", lambda: store.login(username, password, PEER), 401)
    store.disable_account(result["account_id"])
    assert_error("invalid_credentials", lambda: store.login("Aresitos56", PASSWORD, PEER), 401)
    assert [call[0] for call in store.hasher.calls] == ["verify"] * 3
    assert store.hasher.calls[0][1] == store.hasher.dummy_hash
    assert_error("invalid_credentials", lambda: store.authenticate(result["access_token"]), 401)


def test_authentication_does_no_kdf_or_enrollment_and_logout_is_idempotent(store, db):
    result = register(store)
    store.hasher.calls.clear()
    for _ in range(5):
        assert store.authenticate(result["access_token"]) == result["account_id"]
    assert not store.hasher.calls
    for token in ("", "st1_fake", "Bearer " + result["access_token"], " " + result["access_token"], None):
        assert_error("invalid_credentials", lambda: store.authenticate(token), 401)
    assert row_count(db[0], "auth_accounts") == 1
    assert store.logout(result["access_token"]) == {"signed_out": True}
    assert store.logout(result["access_token"]) == {"signed_out": True}
    assert_error("invalid_credentials", lambda: store.authenticate(result["access_token"]), 401)


def test_sessions_expire_absolutely_and_never_extend_on_authenticate(store, db):
    result = register(store)
    db[1][0] += LOCAL_SESSION_MS - 1
    assert store.authenticate(result["access_token"]) == result["account_id"]
    db[1][0] += 1
    assert_error("invalid_credentials", lambda: store.authenticate(result["access_token"]), 401)


def test_maximum_eight_sessions_revokes_oldest_without_changing_identity(store, db):
    results = [register(store)]
    for _ in range(8):
        db[1][0] += 1
        results.append(store.login("Aresitos56", PASSWORD, PEER))
    assert row_count(db[0], "auth_sessions") == 8
    assert_error("invalid_credentials", lambda: store.authenticate(results[0]["access_token"]), 401)
    for result in results[1:]:
        assert store.authenticate(result["access_token"]) == results[0]["account_id"]


def test_recovery_keeps_identity_revokes_sessions_and_requires_normal_login(store, db):
    first = register(store)
    second = store.login("Aresitos56", PASSWORD, PEER)
    changed = store.recover("ARESITOS56", first["recovery_code"], NEW_PASSWORD, PEER)
    assert changed["account_id"] == first["account_id"]
    assert changed["password_changed"] is True
    assert changed["require_login"] is True
    assert "access_token" not in changed
    assert changed["recovery_code"] != first["recovery_code"]
    assert row_count(db[0], "auth_sessions") == 0
    for result in (first, second):
        assert_error("invalid_credentials", lambda: store.authenticate(result["access_token"]), 401)
    assert_error("invalid_credentials", lambda: store.login("Aresitos56", PASSWORD, PEER), 401)
    assert store.login("Aresitos56", NEW_PASSWORD, PEER)["account_id"] == first["account_id"]
    assert_error("invalid_credentials", lambda: store.recover("Aresitos56", first["recovery_code"], PASSWORD, PEER), 401)
    restarted = AccountStore(db[0], hasher=FastHasher())
    assert restarted.recover("Aresitos56", changed["recovery_code"], PASSWORD, PEER)["account_id"] == first["account_id"]


def test_wrong_recovery_code_cannot_reset_password_or_create_session(store, db):
    first = register(store)
    for username, recovery in (("MissingUser", first["recovery_code"]), ("Aresitos56", "rc1_bad")):
        assert_error("invalid_credentials", lambda: store.recover(username, recovery, NEW_PASSWORD, PEER), 401)
    assert row_count(db[0], "auth_sessions") == 1
    assert store.login("Aresitos56", PASSWORD, PEER)["account_id"] == first["account_id"]


def test_concurrent_recovery_code_use_only_succeeds_once(store, db, monkeypatch):
    first = register(store)
    barrier = threading.Barrier(2)
    original = store._new_recovery
    def synchronized_recovery():
        value = original()
        barrier.wait(timeout=5)
        return value
    monkeypatch.setattr(store, "_new_recovery", synchronized_recovery)
    def attempt(index):
        try:
            return store.recover("Aresitos56", first["recovery_code"], NEW_PASSWORD + str(index), f"127.0.0.{index + 1}")
        except AccountError as error:
            return error
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert [result.code for result in results if isinstance(result, AccountError)] == ["invalid_credentials"]
    assert row_count(db[0], "auth_sessions") == 0
    con = db[0].connect()
    try:
        assert con.execute("SELECT credential_version FROM auth_accounts").fetchone()[0] == 2
    finally:
        con.close()


@pytest.mark.parametrize("mutation", ["recover", "disable"])
def test_login_cannot_mint_session_after_concurrent_reset_or_disable(store, db, monkeypatch, mutation):
    first = register(store)
    verified, resume = threading.Event(), threading.Event()
    original = store._kdf
    def pause_verified(method, *args):
        result = original(method, *args)
        if method == "verify":
            verified.set()
            assert resume.wait(5)
        return result
    monkeypatch.setattr(store, "_kdf", pause_verified)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(store.login, "Aresitos56", PASSWORD, PEER)
        assert verified.wait(5)
        if mutation == "recover":
            store.recover("Aresitos56", first["recovery_code"], NEW_PASSWORD, PEER)
        else:
            store.disable_account(first["account_id"])
        resume.set()
        assert_error("invalid_credentials", future.result, 401)
    assert row_count(db[0], "auth_sessions") == 0


def test_password_change_requires_current_password_and_rotates_every_secret(store, db):
    first = register(store)
    second = store.login("Aresitos56", PASSWORD, PEER)
    assert_error("invalid_credentials", lambda: store.change_password(first["access_token"], NEW_PASSWORD, NEW_PASSWORD, PEER), 401)
    changed = store.change_password(first["access_token"], PASSWORD, NEW_PASSWORD, PEER)
    assert changed["account_id"] == first["account_id"]
    assert changed["recovery_code"] != first["recovery_code"]
    assert row_count(db[0], "auth_sessions") == 1
    for result in (first, second):
        assert_error("invalid_credentials", lambda: store.authenticate(result["access_token"]), 401)
    assert store.authenticate(changed["access_token"]) == first["account_id"]
    assert_error("invalid_credentials", lambda: store.recover("Aresitos56", first["recovery_code"], PASSWORD, PEER), 401)


def test_password_change_cannot_complete_after_logout_during_hash(store, db, monkeypatch):
    first = register(store)
    hashed, resume = threading.Event(), threading.Event()
    original = store._kdf
    def pause_hash(method, *args):
        result = original(method, *args)
        if method == "hash":
            hashed.set()
            assert resume.wait(5)
        return result
    monkeypatch.setattr(store, "_kdf", pause_hash)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(store.change_password, first["access_token"], PASSWORD, NEW_PASSWORD, PEER)
        assert hashed.wait(5)
        store.logout(first["access_token"])
        resume.set()
        assert_error("invalid_credentials", future.result, 401)
    assert store.login("Aresitos56", PASSWORD, PEER)["account_id"] == first["account_id"]


def test_new_google_accounts_require_invitation_and_never_link_by_username(store, db):
    first = register(store)
    expires = db[1][0] + 60 * 60_000
    assert_error("invalid_invitation", lambda: store.google_login("Aresitos56", None, PEER, expires_at_ms=expires), 403)
    invite = store.issue_invitation()["invitation"]
    google = store.google_login("Aresitos56", invite, PEER, expires_at_ms=expires)
    assert google["account_id"] != first["account_id"]
    assert "username" not in google and "recovery_code" not in google
    assert google["expires_at_ms"] == db[1][0] + GOOGLE_SESSION_MS
    again = store.google_login("Aresitos56", None, PEER, expires_at_ms=expires)
    assert again["account_id"] == google["account_id"]
    assert_error("invalid_invitation", lambda: store.google_login("AnotherGoogle", invite, PEER, expires_at_ms=expires), 403)
    assert row_count(db[0], "auth_accounts") == 2


@pytest.mark.parametrize("table", ["hearts", "device_hearts", "completions", "portable_settings"])
def test_google_bootstrap_requires_actual_premigration_state_and_calls_enroll_exactly_once(db, table):
    database, clock = db
    con = database.connect()
    try:
        if table == "hearts":
            con.execute("INSERT INTO hearts VALUES('old-uid','programming',0,?,1)", (clock[0],))
        elif table == "device_hearts":
            con.execute("INSERT INTO device_hearts VALUES('old-uid','device','programming',0,?,1)", (clock[0],))
        elif table == "completions":
            con.execute("INSERT INTO completions VALUES('old-uid','lesson','course','lesson',?)", (clock[0],))
        else:
            con.execute("INSERT INTO portable_settings VALUES('old-uid','reader','{}',1,?)", (clock[0],))
    finally:
        con.close()
    calls = []
    def enroll(con, account_id, legacy_uid, now):
        assert con.in_transaction
        calls.append((account_id, legacy_uid, now))
    store = AccountStore(database, on_enroll=enroll, hasher=FastHasher(), firebase_project="test-project")
    google = store.google_login("old-uid", None, PEER, expires_at_ms=clock[0] + DAY_MS)
    assert google["account_id"] != "old-uid"
    assert calls == [(google["account_id"], "old-uid", clock[0])]
    restarted = AccountStore(database, on_enroll=enroll, hasher=FastHasher(), firebase_project="test-project")
    assert restarted.google_login("old-uid", None, PEER, expires_at_ms=clock[0] + DAY_MS)["account_id"] == google["account_id"]
    assert len(calls) == 1
    # Old endpoint writes after migration cannot invent invitation exemptions.
    database.hearts("post-migration-uid", "programming")
    assert_error("invalid_invitation", lambda: restarted.google_login("post-migration-uid", None, PEER, expires_at_ms=clock[0] + DAY_MS), 403)


def test_google_token_expiry_persisted_project_and_disabled_mapping(store, db):
    google = store.google_login("google-uid", store.issue_invitation()["invitation"], PEER, expires_at_ms=db[1][0] + 1000)
    assert google["expires_at_ms"] == db[1][0] + 1000
    db[1][0] += 1000
    assert_error("invalid_credentials", lambda: store.authenticate(google["access_token"]), 401)
    assert_error("invalid_credentials", lambda: store.google_login("google-uid", None, PEER, expires_at_ms=db[1][0]), 401)
    with pytest.raises(RuntimeError, match="project differs"):
        AccountStore(db[0], hasher=FastHasher(), firebase_project="other-project")
    unconfigured = AccountStore(db[0], hasher=FastHasher())
    assert_error("invalid_credentials", lambda: unconfigured.google_login("google-uid", None, PEER, expires_at_ms=db[1][0] + DAY_MS), 401)
    store.disable_account(google["account_id"])
    assert_error("invalid_credentials", lambda: store.google_login("google-uid", None, PEER, expires_at_ms=db[1][0] + DAY_MS), 401)


def test_google_enrollment_failure_rolls_back_mapping_invitation_and_account(db):
    def fail(*args):
        raise RuntimeError("google enrollment failed")
    store = AccountStore(db[0], on_enroll=fail, hasher=FastHasher(), firebase_project="test-project")
    invitation = store.issue_invitation()["invitation"]
    with pytest.raises(RuntimeError, match="enrollment failed"):
        store.google_login("google-uid", invitation, PEER, expires_at_ms=db[1][0] + DAY_MS)
    assert row_count(db[0], "auth_accounts") == row_count(db[0], "auth_google") == 0
    store.on_enroll = None
    assert store.google_login("google-uid", invitation, PEER, expires_at_ms=db[1][0] + DAY_MS)["account_id"]


def test_per_username_rate_limit_survives_restart_and_precedes_kdf(store, db):
    for i in range(10):
        assert_error("invalid_credentials", lambda: store.login("UnknownUser", PASSWORD, f"127.0.0.{i + 1}"), 401)
    count = len(store.hasher.calls)
    error = assert_error("rate_limited", lambda: store.login("UNKNOWNuser", PASSWORD, "10.0.0.1"), 429)
    assert error.retry_after == 900
    assert len(store.hasher.calls) == count
    restarted = AccountStore(db[0], hasher=FastHasher())
    assert_error("rate_limited", lambda: restarted.login("unknownuser", PASSWORD, "10.0.0.2"), 429)
    assert not restarted.hasher.calls
    db[1][0] += 15 * 60_000
    assert_error("invalid_credentials", lambda: restarted.login("UnknownUser", PASSWORD, PEER), 401)
    assert len(restarted.hasher.calls) == 1


def test_peer_and_global_limit_stop_rotating_usernames(store, db):
    for i in range(40):
        assert_error("invalid_credentials", lambda: store.login(f"Missing{i:03}", PASSWORD, PEER), 401)
    assert_error("rate_limited", lambda: store.login("MoreMissing", PASSWORD, PEER), 429)
    for i in range(80):
        assert_error("invalid_credentials", lambda: store.login(f"Others{i:03}", PASSWORD, f"10.0.0.{i + 1}"), 401)
    assert_error("rate_limited", lambda: store.login("GlobalStop", PASSWORD, "192.0.2.1"), 429)
    assert len(store.hasher.calls) == 120
    assert row_count(db[0], "auth_rate_limits") <= 1 + 121 + 120


def test_ipv6_peer_buckets_group_prefixes_and_reject_untrusted_aliases(store):
    assert store._peer_key("::ffff:127.0.0.1") == store._peer_key("127.0.0.1")
    assert store._peer_key("2001:db8:1:2::1") == store._peer_key("2001:db8:1:2::ffff")
    assert store._peer_key("bad-host") == store._peer_key("different-bad-host") == "unknown-peer"


def test_rate_limit_table_capacity_is_fail_closed_and_cleanup_is_bounded(store, db):
    con = db[0].connect()
    try:
        con.executemany("INSERT INTO auth_rate_limits VALUES(?,1,?)", ((f"seed-{i}", db[1][0] + DAY_MS) for i in range(accounts.MAX_RATE_BUCKETS)))
    finally:
        con.close()
    assert_error("authentication_busy", lambda: store.login("Aresitos56", PASSWORD, PEER), 503)
    assert not store.hasher.calls
    assert row_count(db[0], "auth_rate_limits") == accounts.MAX_RATE_BUCKETS
    db[1][0] += DAY_MS
    assert_error("invalid_credentials", lambda: store.login("Aresitos56", PASSWORD, PEER), 401)
    assert row_count(db[0], "auth_rate_limits") == accounts.MAX_RATE_BUCKETS - 128 + 3


def test_kdf_gate_is_global_nonblocking_and_never_holds_sql_transaction(store, db):
    first = register(store)
    entered, release = threading.Event(), threading.Event()
    class BlockingHasher(FastHasher):
        def verify(self, password, encoded):
            entered.set()
            assert release.wait(5)
            return super().verify(password, encoded)
    store.hasher = BlockingHasher()
    another = AccountStore(db[0], hasher=FastHasher())
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(store.login, "Aresitos56", PASSWORD, PEER)
        try:
            assert entered.wait(5)
            # A second instance is rejected immediately, not queued for hashing.
            assert_error("authentication_busy", lambda: another.login("Aresitos56", PASSWORD, PEER), 503)
            assert not another.hasher.calls
            # The SQLite writer is free while the expensive password check runs.
            con = db[0].connect()
            try:
                con.execute("PRAGMA busy_timeout=100")
                con.execute("BEGIN IMMEDIATE")
                con.rollback()
            finally:
                con.close()
            assert another.authenticate(first["access_token"]) == first["account_id"]
        finally:
            release.set()
        assert future.result()["account_id"] == first["account_id"]


def test_kdf_gate_releases_after_hasher_failure(store):
    register(store)
    class BrokenHasher(FastHasher):
        def verify(self, *args):
            raise RuntimeError("KDF unavailable")
    store.hasher = BrokenHasher()
    with pytest.raises(RuntimeError, match="KDF unavailable"):
        store.login("Aresitos56", PASSWORD, PEER)
    store.hasher = FastHasher()
    assert store.login("Aresitos56", PASSWORD, PEER)["access_token"]


def test_additive_schema_refuses_unknown_version_or_missing_auth_table(store, db):
    con = db[0].connect()
    try:
        con.execute("UPDATE auth_schema_version SET version=999")
    finally:
        con.close()
    with pytest.raises(RuntimeError, match="Unsupported authentication schema"):
        AccountStore(db[0], hasher=FastHasher())
    con = db[0].connect()
    try:
        con.execute("UPDATE auth_schema_version SET version=1")
        con.execute("DROP TABLE auth_google")
    finally:
        con.close()
    with pytest.raises(RuntimeError, match="table missing"):
        AccountStore(db[0], hasher=FastHasher())


def test_real_scrypt_roundtrip_salt_exact_password_and_fixed_parameters(monkeypatch):
    hasher = ScryptHasher()
    original = hashlib.scrypt
    calls = []
    def observed(password, **kwargs):
        calls.append({key: value for key, value in kwargs.items() if key != "salt"})
        return original(password, **kwargs)
    monkeypatch.setattr(hashlib, "scrypt", observed)
    password = "  an exact real password  "
    encoded = hasher.hash(password)
    assert encoded.startswith("scrypt$v1$32768$8$3$")
    assert password not in encoded
    assert hasher.verify(password, encoded)
    assert not hasher.verify(password.strip(), encoded)
    assert not hasher.verify(password, hasher.dummy_hash)
    # Malicious stored parameters never control memory or work factors.
    assert not hasher.verify(password, encoded.replace("32768", "1073741824"))
    another = hasher.hash(password)
    assert encoded != another
    assert len(calls) == 6
    assert all(call == {"n": 32768, "r": 8, "p": 3, "maxmem": 64 * 1024 * 1024, "dklen": 32} for call in calls)


def test_real_scrypt_accepts_maximum_unicode_and_rejects_noncanonical_format():
    hasher = ScryptHasher()
    password = "😀" * 128
    encoded = hasher.hash(password)
    assert hasher.verify(password, encoded)
    assert not hasher.verify(password, encoded + "=")
    assert_error("invalid_password", lambda: hasher.hash(password + "😀"), 422)
