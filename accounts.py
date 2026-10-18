"""Persistent, invitation-only accounts for ServerTec.

Passwords, bearer tokens, invitation values and recovery codes never enter SQLite
in plaintext. Callers must pass the actual socket peer and must verify Firebase
tokens before google_login(). No email-based account linking is performed.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import hmac
import ipaddress
import math
import re
import secrets
import sqlite3
import threading


DAY_MS = 86_400_000
LOCAL_SESSION_MS = 30 * DAY_MS
GOOGLE_SESSION_MS = 15 * 60_000
MAX_SESSIONS = 8
MAX_RATE_BUCKETS = 4096
MAX_ACTIVE_INVITATIONS = 1000
SCRYPT_N, SCRYPT_R, SCRYPT_P = 32768, 8, 3
SCRYPT_MAXMEM = 64 * 1024 * 1024
_KDF_GATE = threading.BoundedSemaphore(1)
_USERNAME = re.compile(r"[A-Za-z0-9_]{3,32}", re.ASCII)
_OPAQUE = re.compile(r"[A-Za-z0-9_-]{43}", re.ASCII)
_HASH = re.compile(r"scrypt\$v1\$32768\$8\$3\$([A-Za-z0-9_-]{22})\$([A-Za-z0-9_-]{43})", re.ASCII)
_DUMMY_PASSWORD = "not a real account password"


class AccountError(Exception):
    def __init__(self, code: str, status: int = 409, retry_after: int | None = None):
        self.code, self.status, self.retry_after = code, status, retry_after
        super().__init__(code)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _password_bytes(password: str) -> bytes:
    if not isinstance(password, str) or not 15 <= len(password) <= 128:
        raise AccountError("invalid_password", 422)
    try:
        value = password.encode("utf-8", errors="strict")
    except UnicodeError:
        raise AccountError("invalid_password", 422) from None
    if len(value) > 512:
        raise AccountError("invalid_password", 422)
    return value


def _username(username: str) -> tuple[str, str]:
    if not isinstance(username, str) or _USERNAME.fullmatch(username) is None:
        raise AccountError("invalid_username", 422)
    return username, username.lower()


def _opaque_digest(value: str, prefix: str) -> str | None:
    if not isinstance(value, str) or not value.startswith(prefix):
        return None
    body = value[len(prefix):]
    if _OPAQUE.fullmatch(body) is None:
        return None
    # Reject non-canonical final base64 bits, rather than allowing token aliases.
    try:
        decoded = base64.urlsafe_b64decode(body + "=")
    except (ValueError, TypeError):
        return None
    if len(decoded) != 32 or _b64(decoded) != body:
        return None
    return hashlib.sha256(value.encode("ascii")).hexdigest()


class ScryptHasher:
    """Fixed-cost scrypt; stored parameters cannot request a larger allocation."""

    dummy_hash = "scrypt$v1$32768$8$3$" + _b64(bytes(16)) + "$" + _b64(bytes(32))

    @staticmethod
    def _derive(password: bytes, salt: bytes) -> bytes:
        return hashlib.scrypt(password, salt=salt, n=SCRYPT_N, r=SCRYPT_R,
                              p=SCRYPT_P, maxmem=SCRYPT_MAXMEM, dklen=32)

    def hash(self, password: str) -> str:
        value, salt = _password_bytes(password), secrets.token_bytes(16)
        return "scrypt$v1$32768$8$3$" + _b64(salt) + "$" + _b64(self._derive(value, salt))

    def verify(self, password: str, encoded: str) -> bool:
        value = _password_bytes(password)
        matched = _HASH.fullmatch(encoded) if isinstance(encoded, str) else None
        valid = matched is not None
        salt, expected = bytes(16), bytes(32)
        if matched is not None:
            salt = base64.urlsafe_b64decode(matched[1] + "==")
            expected = base64.urlsafe_b64decode(matched[2] + "=")
            valid = len(salt) == 16 and len(expected) == 32 and _b64(salt) == matched[1] and _b64(expected) == matched[2]
        # Corrupt or unsupported encodings still perform one fixed-cost dummy KDF.
        if not valid:
            salt, expected = bytes(16), bytes(32)
        actual = self._derive(value, salt)
        return hmac.compare_digest(actual, expected) and valid


class AccountStore:
    """Account/session persistence; KDF work always runs outside SQL transactions.

    The injected hasher exists for isolated non-crypto tests; production callers
    should omit it. Recovery never signs the user in automatically. A password
    change authenticated by the current password rotates the calling session.
    """

    def __init__(self, database, on_enroll=None, *, hasher=None, firebase_project: str = ""):
        self.database, self.on_enroll = database, on_enroll
        self.hasher = hasher if hasher is not None else ScryptHasher()
        self.firebase_project = firebase_project
        if not isinstance(firebase_project, str) or len(firebase_project) > 128:
            raise ValueError("Invalid Firebase project configuration")
        self._initialize()

    @contextmanager
    def _connection(self):
        con = self.database.connect()
        try:
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA foreign_keys=ON")
            yield con
        finally:
            con.close()

    @contextmanager
    def _transaction(self):
        with self._connection() as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                yield con
                con.commit()
            except Exception:
                con.rollback()
                raise

    def _now(self) -> int:
        return int(self.database.clock())

    def _initialize(self):
        statements = [
            "CREATE TABLE auth_schema_version(version INTEGER NOT NULL)",
            "CREATE TABLE auth_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)",
            """CREATE TABLE auth_accounts(
                account_id TEXT PRIMARY KEY,username TEXT,username_key TEXT UNIQUE,
                password_hash TEXT,recovery_digest TEXT,credential_version INTEGER NOT NULL,
                disabled INTEGER NOT NULL DEFAULT 0,created_at_ms INTEGER NOT NULL,
                CHECK(credential_version>0),CHECK(disabled IN (0,1)),
                CHECK((username IS NULL AND username_key IS NULL AND password_hash IS NULL AND recovery_digest IS NULL)
                   OR (username IS NOT NULL AND username_key IS NOT NULL AND password_hash IS NOT NULL AND recovery_digest IS NOT NULL)))""",
            """CREATE TABLE auth_google(
                project TEXT NOT NULL,firebase_uid TEXT NOT NULL,account_id TEXT NOT NULL UNIQUE,
                PRIMARY KEY(project,firebase_uid),
                FOREIGN KEY(account_id) REFERENCES auth_accounts(account_id))""",
            """CREATE TABLE auth_invitations(
                invitation_digest TEXT PRIMARY KEY,created_at_ms INTEGER NOT NULL,
                expires_at_ms INTEGER NOT NULL,consumed_by TEXT,consumed_at_ms INTEGER,
                FOREIGN KEY(consumed_by) REFERENCES auth_accounts(account_id))""",
            """CREATE TABLE auth_sessions(
                token_digest TEXT PRIMARY KEY,account_id TEXT NOT NULL,
                credential_version INTEGER NOT NULL,created_at_ms INTEGER NOT NULL,
                expires_at_ms INTEGER NOT NULL,
                FOREIGN KEY(account_id) REFERENCES auth_accounts(account_id))""",
            "CREATE INDEX auth_sessions_expiry ON auth_sessions(expires_at_ms)",
            "CREATE INDEX auth_sessions_account ON auth_sessions(account_id,created_at_ms)",
            "CREATE INDEX auth_invitation_expiry ON auth_invitations(expires_at_ms)",
            """CREATE TABLE auth_rate_limits(
                bucket TEXT PRIMARY KEY,used INTEGER NOT NULL,expires_at_ms INTEGER NOT NULL)""",
            "CREATE INDEX auth_rates_expiry ON auth_rate_limits(expires_at_ms)",
            "CREATE TABLE auth_legacy_eligible(firebase_uid TEXT PRIMARY KEY)",
        ]
        with self._transaction() as con:
            exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='auth_schema_version'").fetchone()
            if exists is None:
                for statement in statements:
                    con.execute(statement)
                con.execute("INSERT INTO auth_schema_version VALUES(1)")
                # Capture once. Rows created by old endpoints AFTER this migration
                # cannot later bypass the invitation requirement.
                for table in ("hearts", "device_hearts", "completions", "portable_settings"):
                    present = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
                    if present:
                        con.execute(f"INSERT OR IGNORE INTO auth_legacy_eligible SELECT DISTINCT uid FROM {table}")
            else:
                if [tuple(row) for row in con.execute("SELECT version FROM auth_schema_version")] != [(1,)]:
                    raise RuntimeError("Unsupported authentication schema; do not overwrite it")
                for table in ("auth_meta", "auth_accounts", "auth_google", "auth_invitations", "auth_sessions", "auth_rate_limits", "auth_legacy_eligible"):
                    if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is None:
                        raise RuntimeError("Authentication table missing; do not recreate it")
            configured = con.execute("SELECT value FROM auth_meta WHERE key='firebase_project'").fetchone()
            if self.firebase_project:
                if configured is not None and configured["value"] != self.firebase_project:
                    raise RuntimeError("Firebase project differs from the persisted account namespace")
                con.execute("INSERT OR IGNORE INTO auth_meta VALUES('firebase_project',?)", (self.firebase_project,))

    @staticmethod
    def _peer_key(peer: str) -> str:
        try:
            address = ipaddress.ip_address(peer)
            if isinstance(address, ipaddress.IPv6Address):
                if address.ipv4_mapped:
                    return str(address.ipv4_mapped)
                return str(ipaddress.ip_network((address, 64), strict=False))
            return str(address)
        except (TypeError, ValueError):
            # Missing/unparseable socket identity shares one bucket; it must not
            # provide an unbounded attacker-selected namespace.
            return "unknown-peer"

    def _limit(self, operation: str, subject: str, peer: str):
        if operation == "register":
            window, global_quota, peer_quota, subject_quota = 60 * 60_000, 30, 5, 5
        elif operation in ("recover", "change"):
            window, global_quota, peer_quota, subject_quota = 60 * 60_000, 60, 10, 5
        else:
            window, global_quota, peer_quota, subject_quota = 15 * 60_000, 120, 40, 10
        def key(scope, value):
            return operation + ":" + scope + ":" + hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
        limits = [(key("global", "all"), global_quota),
                  (key("peer", self._peer_key(peer)), peer_quota),
                  (key("subject", subject[:256]), subject_quota)]
        rejection = None
        with self._transaction() as con:
            now = self._now()
            con.execute("DELETE FROM auth_rate_limits WHERE bucket IN (SELECT bucket FROM auth_rate_limits WHERE expires_at_ms<=? ORDER BY expires_at_ms LIMIT 128)", (now,))
            count = con.execute("SELECT COUNT(*) FROM auth_rate_limits").fetchone()[0]
            rows = {bucket: con.execute("SELECT used,expires_at_ms FROM auth_rate_limits WHERE bucket=?", (bucket,)).fetchone() for bucket, _ in limits}
            additions = sum(row is None for row in rows.values())
            if count + additions > MAX_RATE_BUCKETS:
                rejection = AccountError("authentication_busy", 503, 60)
            else:
                for bucket, quota in limits:
                    row = rows[bucket]
                    if row and row["expires_at_ms"] > now and row["used"] >= quota:
                        retry = max(1, math.ceil((row["expires_at_ms"] - now) / 1000))
                        rejection = AccountError("rate_limited", 429, retry)
                        break
                if rejection is None:
                    for bucket, _ in limits:
                        row = rows[bucket]
                        if row is None or row["expires_at_ms"] <= now:
                            con.execute("INSERT INTO auth_rate_limits VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET used=1,expires_at_ms=excluded.expires_at_ms", (bucket, now + window))
                        else:
                            con.execute("UPDATE auth_rate_limits SET used=used+1 WHERE bucket=?", (bucket,))
        if rejection:
            raise rejection

    def _kdf(self, method: str, *args):
        if not _KDF_GATE.acquire(blocking=False):
            raise AccountError("authentication_busy", 503, 2)
        try:
            return getattr(self.hasher, method)(*args)
        finally:
            _KDF_GATE.release()

    @staticmethod
    def _new_account_id() -> str:
        return "acct_" + secrets.token_urlsafe(24)

    @staticmethod
    def _new_recovery() -> tuple[str, str]:
        value = "rc1_" + secrets.token_urlsafe(32)
        return value, _opaque_digest(value, "rc1_")

    @staticmethod
    def _require_invitation(con, invitation: str, now: int) -> str:
        digest = _opaque_digest(invitation, "iv1_")
        row = con.execute("SELECT consumed_by,expires_at_ms FROM auth_invitations WHERE invitation_digest=?", (digest,)).fetchone() if digest else None
        if row is None or row["consumed_by"] is not None or row["expires_at_ms"] <= now:
            raise AccountError("invalid_invitation", 403)
        return digest

    def issue_invitation(self, *, expires_in_ms: int = 7 * DAY_MS) -> dict:
        """Administrative local operation; never expose this as a public route."""
        if type(expires_in_ms) is not int or not 60_000 <= expires_in_ms <= 30 * DAY_MS:
            raise AccountError("invalid_invitation_lifetime", 422)
        invitation = "iv1_" + secrets.token_urlsafe(32)
        digest = _opaque_digest(invitation, "iv1_")
        with self._transaction() as con:
            now = self._now()
            con.execute("DELETE FROM auth_invitations WHERE invitation_digest IN (SELECT invitation_digest FROM auth_invitations WHERE expires_at_ms<=? ORDER BY expires_at_ms LIMIT 128)", (now,))
            active = con.execute("SELECT COUNT(*) FROM auth_invitations WHERE consumed_by IS NULL AND expires_at_ms>?", (now,)).fetchone()[0]
            if active >= MAX_ACTIVE_INVITATIONS:
                raise AccountError("invitation_capacity", 409)
            con.execute("INSERT INTO auth_invitations VALUES(?,?,?,NULL,NULL)", (digest, now, now + expires_in_ms))
        return {"invitation": invitation, "expires_at_ms": now + expires_in_ms}

    def _session(self, con, row, now: int, expires_at_ms: int | None = None) -> dict:
        expires_at_ms = now + LOCAL_SESSION_MS if expires_at_ms is None else expires_at_ms
        if expires_at_ms <= now:
            raise AccountError("invalid_credentials", 401)
        token = "st1_" + secrets.token_urlsafe(32)
        digest = _opaque_digest(token, "st1_")
        con.execute("DELETE FROM auth_sessions WHERE token_digest IN (SELECT token_digest FROM auth_sessions WHERE expires_at_ms<=? ORDER BY expires_at_ms LIMIT 64)", (now,))
        con.execute("INSERT INTO auth_sessions VALUES(?,?,?,?,?)", (digest, row["account_id"], row["credential_version"], now, expires_at_ms))
        con.execute("DELETE FROM auth_sessions WHERE account_id=? AND token_digest NOT IN (SELECT token_digest FROM auth_sessions WHERE account_id=? ORDER BY created_at_ms DESC,rowid DESC LIMIT ?)", (row["account_id"], row["account_id"], MAX_SESSIONS))
        result = {"account_id": row["account_id"], "access_token": token,
                  "token_type": "Bearer", "expires_at_ms": expires_at_ms}
        if row["username"] is not None:
            result["username"] = row["username"]
        return result

    def register(self, username: str, password: str, invitation: str, peer: str) -> dict:
        display, normalized = _username(username)
        _password_bytes(password)
        self._limit("register", normalized, peer)
        # An invalid invite cannot trigger an expensive hash or reveal usernames.
        with self._connection() as con:
            self._require_invitation(con, invitation, self._now())
        encoded = self._kdf("hash", password)
        account_id = self._new_account_id()
        recovery, recovery_digest = self._new_recovery()
        with self._transaction() as con:
            # BEGIN IMMEDIATE may wait for another writer. Read the clock only
            # after acquiring it so a just-expired invite cannot be consumed.
            now = self._now()
            invite_digest = self._require_invitation(con, invitation, now)
            if con.execute("SELECT 1 FROM auth_accounts WHERE username_key=?", (normalized,)).fetchone():
                raise AccountError("username_unavailable", 409)
            con.execute("INSERT INTO auth_accounts VALUES(?,?,?,?,?,1,0,?)", (account_id, display, normalized, encoded, recovery_digest, now))
            con.execute("UPDATE auth_invitations SET consumed_by=?,consumed_at_ms=? WHERE invitation_digest=?", (account_id, now, invite_digest))
            if self.on_enroll:
                self.on_enroll(con, account_id, None, now)
            row = con.execute("SELECT * FROM auth_accounts WHERE account_id=?", (account_id,)).fetchone()
            result = self._session(con, row, now)
        result["recovery_code"] = recovery
        return result

    def _login_material(self, username, password):
        valid = True
        try:
            _, normalized = _username(username)
        except AccountError:
            normalized, valid = "invalid-username", False
        try:
            _password_bytes(password)
        except AccountError:
            password, valid = _DUMMY_PASSWORD, False
        return normalized, password, valid

    def login(self, username: str, password: str, peer: str) -> dict:
        normalized, candidate, valid_input = self._login_material(username, password)
        self._limit("login", normalized, peer)
        with self._connection() as con:
            row = con.execute("SELECT * FROM auth_accounts WHERE username_key=?", (normalized,)).fetchone() if valid_input else None
        encoded = row["password_hash"] if row is not None else self.hasher.dummy_hash
        verified = self._kdf("verify", candidate, encoded)
        if row is None or not valid_input or not verified or row["disabled"]:
            raise AccountError("invalid_credentials", 401)
        with self._transaction() as con:
            current = con.execute("SELECT * FROM auth_accounts WHERE account_id=?", (row["account_id"],)).fetchone()
            if not self._same_credential(row, current):
                raise AccountError("invalid_credentials", 401)
            return self._session(con, current, self._now())

    @staticmethod
    def _same_credential(previous, current) -> bool:
        return (current is not None and not current["disabled"]
                and current["credential_version"] == previous["credential_version"]
                and hmac.compare_digest(current["password_hash"] or "", previous["password_hash"] or ""))

    def google_login(self, firebase_uid: str, invitation: str | None, peer: str, *, expires_at_ms: int) -> dict:
        """Exchange an already verified Google-provider Firebase identity.

        The short local session cannot outlive its verified ID token. Revocation
        at Firebase is not polled here; operators can disable the internal account.
        """
        now = self._now()
        if (not self.firebase_project or not isinstance(firebase_uid, str)
                or not 1 <= len(firebase_uid) <= 128
                or type(expires_at_ms) is not int or expires_at_ms <= now):
            raise AccountError("invalid_credentials", 401)
        self._limit("google", self.firebase_project + ":" + firebase_uid, peer)
        with self._transaction() as con:
            now = self._now()
            row = con.execute("SELECT a.* FROM auth_accounts a JOIN auth_google g ON a.account_id=g.account_id WHERE g.project=? AND g.firebase_uid=?", (self.firebase_project, firebase_uid)).fetchone()
            if row is None:
                legacy = con.execute("SELECT 1 FROM auth_legacy_eligible WHERE firebase_uid=?", (firebase_uid,)).fetchone() is not None
                invite_digest = None if legacy else self._require_invitation(con, invitation, now)
                account_id = self._new_account_id()
                con.execute("INSERT INTO auth_accounts VALUES(?,NULL,NULL,NULL,NULL,1,0,?)", (account_id, now))
                con.execute("INSERT INTO auth_google VALUES(?,?,?)", (self.firebase_project, firebase_uid, account_id))
                if invite_digest:
                    con.execute("UPDATE auth_invitations SET consumed_by=?,consumed_at_ms=? WHERE invitation_digest=?", (account_id, now, invite_digest))
                if self.on_enroll:
                    self.on_enroll(con, account_id, firebase_uid if legacy else None, now)
                if legacy:
                    con.execute("DELETE FROM auth_legacy_eligible WHERE firebase_uid=?", (firebase_uid,))
                row = con.execute("SELECT * FROM auth_accounts WHERE account_id=?", (account_id,)).fetchone()
            if row["disabled"]:
                raise AccountError("invalid_credentials", 401)
            now = self._now()
            return self._session(con, row, now, min(now + GOOGLE_SESSION_MS, expires_at_ms))

    def _authenticated_row(self, con, token: str, now: int):
        digest = _opaque_digest(token, "st1_")
        row = con.execute("SELECT a.* FROM auth_sessions s JOIN auth_accounts a ON s.account_id=a.account_id WHERE s.token_digest=? AND s.expires_at_ms>? AND a.disabled=0 AND s.credential_version=a.credential_version", (digest, now)).fetchone() if digest else None
        if row is None:
            raise AccountError("invalid_credentials", 401)
        return row

    def authenticate(self, token: str) -> str:
        """Return an existing identity; never create a wallet or new account."""
        with self._connection() as con:
            return self._authenticated_row(con, token, self._now())["account_id"]

    def logout(self, token: str):
        digest = _opaque_digest(token, "st1_")
        if digest:
            with self._transaction() as con:
                con.execute("DELETE FROM auth_sessions WHERE token_digest=?", (digest,))
        return {"signed_out": True}

    def recover(self, username: str, recovery_code: str, new_password: str, peer: str) -> dict:
        """Rotate password and recovery code atomically; require normal login."""
        _, normalized = _username(username)
        _password_bytes(new_password)
        self._limit("recover", normalized, peer)
        recovery_digest = _opaque_digest(recovery_code, "rc1_")
        with self._connection() as con:
            row = con.execute("SELECT * FROM auth_accounts WHERE username_key=?", (normalized,)).fetchone()
        if (row is None or row["disabled"] or recovery_digest is None
                or not hmac.compare_digest(row["recovery_digest"] or "", recovery_digest)):
            raise AccountError("invalid_credentials", 401)
        encoded = self._kdf("hash", new_password)
        recovery, replacement_digest = self._new_recovery()
        with self._transaction() as con:
            current = con.execute("SELECT * FROM auth_accounts WHERE account_id=?", (row["account_id"],)).fetchone()
            if (not self._same_credential(row, current)
                    or not hmac.compare_digest(current["recovery_digest"] or "", recovery_digest)):
                raise AccountError("invalid_credentials", 401)
            con.execute("UPDATE auth_accounts SET password_hash=?,recovery_digest=?,credential_version=credential_version+1 WHERE account_id=?", (encoded, replacement_digest, row["account_id"]))
            con.execute("DELETE FROM auth_sessions WHERE account_id=?", (row["account_id"],))
        return {"account_id": row["account_id"], "password_changed": True,
                "recovery_code": recovery, "require_login": True}

    # The descriptive name is kept as an alias for non-HTTP callers.
    recovery = recover

    def change_password(self, token: str, current_password: str, new_password: str, peer: str) -> dict:
        _password_bytes(new_password)
        with self._connection() as con:
            row = self._authenticated_row(con, token, self._now())
        self._limit("change", row["account_id"], peer)
        candidate, valid_input = current_password, True
        try:
            _password_bytes(current_password)
        except AccountError:
            candidate, valid_input = _DUMMY_PASSWORD, False
        encoded = row["password_hash"] or self.hasher.dummy_hash
        verified = self._kdf("verify", candidate, encoded)
        if row["password_hash"] is None or not valid_input or not verified:
            raise AccountError("invalid_credentials", 401)
        encoded = self._kdf("hash", new_password)
        recovery, recovery_digest = self._new_recovery()
        with self._transaction() as con:
            current = self._authenticated_row(con, token, self._now())
            if not self._same_credential(row, current):
                raise AccountError("invalid_credentials", 401)
            con.execute("UPDATE auth_accounts SET password_hash=?,recovery_digest=?,credential_version=credential_version+1 WHERE account_id=?", (encoded, recovery_digest, row["account_id"]))
            con.execute("DELETE FROM auth_sessions WHERE account_id=?", (row["account_id"],))
            updated = con.execute("SELECT * FROM auth_accounts WHERE account_id=?", (row["account_id"],)).fetchone()
            result = self._session(con, updated, self._now())
        result.update(password_changed=True, recovery_code=recovery)
        return result

    def disable_account(self, account_id: str):
        """Administrative local operation: revoke all sessions and forbid login."""
        with self._transaction() as con:
            changed = con.execute("UPDATE auth_accounts SET disabled=1,credential_version=credential_version+1 WHERE account_id=?", (account_id,)).rowcount
            if not changed:
                raise AccountError("account_not_found", 404)
            con.execute("DELETE FROM auth_sessions WHERE account_id=?", (account_id,))
