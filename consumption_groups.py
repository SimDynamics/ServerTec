"""Shared FREE-use histories. Never merge credentials, progress or purchases.

One SQLite write transaction resolves identities, checks consent, joins distinct
roots and updates debt. ANDROID_ID is an untrusted, profile-scoped client signal,
not hardware attestation. Only its domain-separated HMAC is stored.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import hmac
import json
import re
import secrets
import sqlite3

from account_ledger import AccountLedger, CAPACITIES, HOUR_MS, LedgerError, _integer
from accounts import AccountError, _opaque_digest

CONFIRMATION_MS = 5 * 60_000
MAX_PENDING = 10_000
MAX_PENDING_PER_ACCOUNT = 8
_NOTICE = {
    "notice_version": 1,
    "title": "Vincular nuevo dispositivo",
    "message": (
        "Detectamos que estás intentando iniciar sesión con tu usuario o correo en un "
        "dispositivo que todavía no está registrado en tu historial.\n\n"
        "Si continúas, este dispositivo se añadirá a tu historial y compartirá los mismos "
        "corazones gratuitos con las cuentas y dispositivos vinculados. Si este dispositivo "
        "ya pertenece a otro historial de corazones, ambos historiales se unirán.\n\n"
        "¿Deseas continuar?"
    ),
    "accept_label": "Sí, continuar",
    "cancel_label": "No, cancelar",
}

_SCHEMA = (
    "CREATE TABLE group_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    """CREATE TABLE consumption_groups(
        group_id TEXT PRIMARY KEY,
        created_ms INTEGER NOT NULL CHECK(typeof(created_ms)='integer' AND created_ms>=0),
        parent_id TEXT REFERENCES consumption_groups(group_id),
        membership_revision INTEGER NOT NULL CHECK(typeof(membership_revision)='integer'
                                                   AND membership_revision>0),
        CHECK(parent_id IS NULL OR parent_id<>group_id))""",
    "CREATE INDEX group_parents ON consumption_groups(parent_id)",
    """CREATE TABLE group_accounts(
        account_id TEXT PRIMARY KEY REFERENCES auth_accounts(account_id),
        group_id TEXT NOT NULL REFERENCES consumption_groups(group_id),
        initial_device INTEGER NOT NULL CHECK(initial_device IN (0,1)))""",
    "CREATE INDEX group_account_roots ON group_accounts(group_id)",
    """CREATE TABLE group_devices(
        device_hash TEXT PRIMARY KEY CHECK(length(device_hash)=64),
        group_id TEXT NOT NULL REFERENCES consumption_groups(group_id))""",
    """CREATE TABLE group_account_devices(
        account_id TEXT NOT NULL REFERENCES auth_accounts(account_id),
        device_hash TEXT NOT NULL REFERENCES group_devices(device_hash),
        linked_ms INTEGER NOT NULL,
        PRIMARY KEY(account_id,device_hash))""",
    """CREATE TABLE group_hearts(
        group_id TEXT NOT NULL REFERENCES consumption_groups(group_id),
        route TEXT NOT NULL CHECK(route IN ('programming','math_physics')),
        debt_ms INTEGER NOT NULL CHECK(typeof(debt_ms)='integer' AND debt_ms>=0),
        anchor_ms INTEGER NOT NULL CHECK(typeof(anchor_ms)='integer' AND anchor_ms>=0),
        revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>0),
        PRIMARY KEY(group_id,route))""",
    """CREATE TABLE group_confirmations(
        digest TEXT PRIMARY KEY,
        session_digest TEXT NOT NULL REFERENCES auth_sessions(token_digest) ON DELETE CASCADE,
        account_id TEXT NOT NULL REFERENCES auth_accounts(account_id),
        device_hash TEXT NOT NULL,
        scope_json TEXT NOT NULL,
        created_ms INTEGER NOT NULL,
        expires_ms INTEGER NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('pending','confirmed','cancelled','stale')),
        UNIQUE(session_digest,device_hash))""",
    "CREATE INDEX group_confirmation_expiry ON group_confirmations(expires_ms)",
    "CREATE INDEX group_confirmation_account ON group_confirmations(account_id)",
    """CREATE TRIGGER group_archive_update BEFORE UPDATE ON account_hearts
        WHEN EXISTS(SELECT 1 FROM group_accounts WHERE account_id=OLD.uid)
        BEGIN SELECT RAISE(ABORT,'account_wallet_is_archived'); END""",
    """CREATE TRIGGER group_archive_delete BEFORE DELETE ON account_hearts
        WHEN EXISTS(SELECT 1 FROM group_accounts WHERE account_id=OLD.uid)
        BEGIN SELECT RAISE(ABORT,'account_wallet_is_archived'); END""",
)
_TABLES = {"group_meta", "consumption_groups", "group_accounts", "group_devices",
           "group_account_devices", "group_hearts", "group_confirmations"}
_TRIGGERS = {"group_archive_update", "group_archive_delete"}


class GroupLedger:
    """Server-side grouping plus consent API, independent of Premium.

    Construct after AccountStore and AccountLedger. Set AccountStore.on_enroll to
    this object's enroll method before accepting requests. Do not run old/new
    server binaries concurrently on the same state directory.
    """

    def __init__(self, database, accounts, legacy_ledger: AccountLedger, devices):
        if accounts.database.path.resolve() != database.path.resolve():
            raise ValueError("Account and group storage must be the same database")
        self.database, self.accounts = database, accounts
        self.legacy, self.devices = legacy_ledger, devices
        callback = accounts.on_enroll
        # Recreating a FastAPI app with the same injected store must not nest hooks.
        owner = getattr(callback, "__self__", None)
        self.prior_enroll = owner.prior_enroll if isinstance(owner, GroupLedger) else callback
        self._initialize()

    @contextmanager
    def transaction(self):
        """Owned, explicitly closed writer; no password KDF or network call here."""
        con = self.database.connect()
        try:
            con.row_factory = sqlite3.Row
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def _now(self):
        return self.legacy._now()

    def _initialize(self):
        with self.transaction() as con:
            objects = {r[0]: r[1] for r in con.execute(
                "SELECT name,type FROM sqlite_master WHERE type IN ('table','trigger')")}
            guard = con.execute("SELECT value FROM auth_meta WHERE key='consumption_groups'").fetchone()
            if "group_meta" not in objects:
                if guard is not None or _TABLES.intersection(objects) or _TRIGGERS.intersection(objects):
                    raise RuntimeError("Shared history schema missing; do not reset state")
                for sql in _SCHEMA:
                    con.execute(sql)
                con.execute("INSERT INTO group_meta VALUES('version','1')")
                # Import each ACCOUNT wallet once, not the archived per-device
                # snapshots from which the earlier AccountLedger already derived it.
                for row in con.execute("SELECT account_id,created_at_ms FROM auth_accounts"):
                    self._import_account(con, row[0], row[1], initial=False)
                con.execute("INSERT INTO auth_meta VALUES('consumption_groups','1')")
            else:
                version = con.execute("SELECT value FROM group_meta WHERE key='version'").fetchone()
                if guard is None or guard[0] != '1' or version is None or version[0] != '1':
                    raise RuntimeError("Unsupported shared history schema")
                if any(objects.get(t) != 'table' for t in _TABLES) or any(
                        objects.get(t) != 'trigger' for t in _TRIGGERS):
                    raise RuntimeError("Shared history object missing; do not recreate it")
                # A legacy binary or a bypassed enrollment hook must not give an
                # existing account a second initial balance on the next login.
                missing = con.execute("""SELECT 1 FROM auth_accounts a LEFT JOIN group_accounts g
                    ON a.account_id=g.account_id WHERE g.account_id IS NULL LIMIT 1""").fetchone()
                if missing:
                    raise RuntimeError("Account missing shared history; explicit repair required")
            pinned = con.execute("SELECT value FROM group_meta WHERE key='device_key_sha256'").fetchone()
            if pinned:
                self._key(con, allow_create=False)

    def _import_account(self, con, account_id, created_ms, *, initial):
        if not _integer(created_ms):
            raise LedgerError("invalid_account_time", 503)
        wallets = self.legacy._wallets(con, account_id)
        # A stable one-to-one initial root also gives deterministic equal-time ties.
        root = "grp_" + hashlib.sha256(account_id.encode()).hexdigest()
        con.execute("INSERT INTO consumption_groups VALUES(?,?,NULL,1)", (root, created_ms))
        con.execute("INSERT INTO group_accounts VALUES(?,?,?)", (account_id, root, int(initial)))
        con.executemany("INSERT INTO group_hearts VALUES(?,?,?,?,?)",
                        [(root, route, *state) for route, state in wallets.items()])

    def enroll(self, con, account_id, legacy_uid, now):
        """Enroll inside the existing account/invitation/session transaction."""
        AccountLedger._require_transaction(con)
        con.execute("SAVEPOINT shared_group_enroll")
        try:
            if self.prior_enroll:
                self.prior_enroll(con, account_id, legacy_uid, now)
            else:
                self.legacy.enroll(con, account_id, legacy_uid, now)
            self._import_account(con, account_id, now, initial=legacy_uid is None)
            con.execute("RELEASE shared_group_enroll")
        except BaseException:
            con.execute("ROLLBACK TO shared_group_enroll")
            con.execute("RELEASE shared_group_enroll")
            raise

    def _key(self, con, *, allow_create):
        pinned = con.execute("SELECT value FROM group_meta WHERE key='device_key_sha256'").fetchone()
        if pinned is None:
            used = con.execute("SELECT 1 FROM group_devices LIMIT 1").fetchone()
            used = used or con.execute("SELECT 1 FROM group_confirmations LIMIT 1").fetchone()
            if used or not allow_create:
                raise LedgerError("device_key_unavailable", 503)
            # Reuse the existing private key and backup format, but not its
            # account-scoped digest. No raw ID is used for initialization.
            if not self.devices.path.exists():
                self.devices.hash("shared-key-bootstrap", "0000000000000000")
        try:
            secret = self.devices.path.read_bytes()
        except OSError:
            raise LedgerError("device_key_unavailable", 503) from None
        if len(secret) != 32:
            raise LedgerError("device_key_unavailable", 503)
        fingerprint = hashlib.sha256(secret).hexdigest()
        if pinned is not None and not hmac.compare_digest(fingerprint, pinned[0]):
            raise LedgerError("device_key_changed", 503)
        if pinned is None:
            con.execute("INSERT INTO group_meta VALUES('device_key_sha256',?)", (fingerprint,))
        return secret

    def _device(self, con, android_id):
        if type(android_id) is not str or re.fullmatch(r"[0-9a-fA-F]{16}", android_id) is None:
            raise LedgerError("invalid_device", 422)
        secret = self._key(con, allow_create=True)
        return hmac.new(secret, b"shared-consumption-v1\0" + android_id.lower().encode('ascii'),
                        hashlib.sha256).hexdigest()

    def _actor(self, con, token, android_id, now):
        row = self.accounts._authenticated_row(con, token, now)
        device = self._device(con, android_id)
        return row['account_id'], _opaque_digest(token, 'st1_'), device

    @staticmethod
    def _root(con, group_id):
        row = con.execute("SELECT * FROM consumption_groups WHERE group_id=?", (group_id,)).fetchone()
        if row is None:
            raise LedgerError("group_state_missing", 503)
        if row['parent_id'] is not None:
            parent = con.execute("SELECT * FROM consumption_groups WHERE group_id=?",
                                 (row['parent_id'],)).fetchone()
            # Merges flatten aliases. Chains or cycles mean corrupted state.
            if parent is None or parent['parent_id'] is not None:
                raise LedgerError("group_state_corrupt", 503)
            row = parent
        if not _integer(row['created_ms']) or not _integer(row['membership_revision'], minimum=1):
            raise LedgerError("group_state_corrupt", 503)
        return row

    def _scope(self, con, account_id, device):
        account = con.execute("SELECT * FROM group_accounts WHERE account_id=?", (account_id,)).fetchone()
        if account is None:
            raise LedgerError("group_state_missing", 503)
        root = self._root(con, account['group_id'])
        match = con.execute("SELECT group_id FROM group_devices WHERE device_hash=?", (device,)).fetchone()
        other = self._root(con, match[0]) if match else None
        linked = con.execute("SELECT 1 FROM group_account_devices WHERE account_id=? AND device_hash=?",
                             (account_id, device)).fetchone() is not None
        if linked and (other is None or root['group_id'] != other['group_id']):
            raise LedgerError("group_state_corrupt", 503)
        return account, root, other, linked

    @staticmethod
    def _scope_signature(root, other):
        def part(row):
            return None if row is None else [row['group_id'], row['membership_revision']]
        return json.dumps([part(root), part(other)], separators=(',', ':'))

    @staticmethod
    def _wallets(con, root):
        rows = con.execute("SELECT route,debt_ms,anchor_ms,revision FROM group_hearts WHERE group_id=?",
                           (root,)).fetchall()
        if len(rows) != len(CAPACITIES):
            raise LedgerError("wallet_state_missing", 503)
        result = {}
        for route, debt, anchor, revision in rows:
            if route not in CAPACITIES or route in result:
                raise LedgerError("wallet_state_corrupt", 503)
            AccountLedger._validate_row(debt, anchor, revision)
            result[route] = debt, anchor, revision
        return result

    def _merge(self, con, left, right, now):
        """Internal: caller already checked consent or initial-device policy."""
        if right is None or left['group_id'] == right['group_id']:
            self._wallets(con, left['group_id'])
            return left['group_id']
        winner, loser = sorted((left, right), key=lambda r: (r['created_ms'], r['group_id']))
        a, b = self._wallets(con, winner['group_id']), self._wallets(con, loser['group_id'])
        for route in CAPACITIES:
            da, aa, ra = a[route]
            db, ab, rb = b[route]
            # Never recover one wallet using another wallet's future anchor.
            debt = max(0, da - max(0, now - aa)) + max(0, db - max(0, now - ab))
            anchor, revision = max(now, aa, ab), max(ra, rb) + 1
            AccountLedger._validate_row(debt, anchor, revision)
            con.execute("UPDATE group_hearts SET debt_ms=?,anchor_ms=?,revision=? WHERE group_id=? AND route=?",
                        (debt, anchor, revision, winner['group_id'], route))
        revision = max(winner['membership_revision'], loser['membership_revision']) + 1
        if not _integer(revision, minimum=1):
            raise LedgerError("group_state_corrupt", 503)
        con.execute("UPDATE consumption_groups SET membership_revision=? WHERE group_id=?",
                    (revision, winner['group_id']))
        # Preserve all old IDs as one-hop aliases, including previous absorptions.
        con.execute("UPDATE consumption_groups SET parent_id=? WHERE group_id=? OR parent_id=?",
                    (winner['group_id'], loser['group_id'], loser['group_id']))
        return winner['group_id']

    def _bind(self, con, account_id, device, root, other, now):
        target = self._merge(con, root, other, now)
        con.execute("INSERT OR IGNORE INTO group_devices VALUES(?,?)", (device, target))
        con.execute("INSERT INTO group_account_devices VALUES(?,?,?)", (account_id, device, now))
        con.execute("UPDATE group_accounts SET initial_device=0 WHERE account_id=?", (account_id,))
        con.execute("UPDATE consumption_groups SET membership_revision=membership_revision+1 WHERE group_id=?", (target,))
        return target

    def _balances(self, con, account_id, root, now):
        return {route: self._update(con, account_id, root, route, now, debit=False) for route in CAPACITIES}

    def _linked_reply(self, con, account_id, root, now, *, replayed=False):
        return {'status': 'linked', 'replayed': replayed, 'account_id': account_id,
                'group_id': root, 'hearts': self._balances(con, account_id, root, now)}

    def prepare(self, token, android_id):
        """Check a pair. Auto-bind only a new account's very first device.

        A known device already used by other accounts receives no new usable
        balance. Old accounts imported without device history require consent.
        """
        with self.transaction() as con:
            now = self._now()
            account_id, session, device = self._actor(con, token, android_id, now)
            account, root, other, linked = self._scope(con, account_id, device)
            if linked:
                return self._linked_reply(con, account_id, root['group_id'], now)
            if account['initial_device']:
                if con.execute("SELECT 1 FROM group_account_devices WHERE account_id=? LIMIT 1", (account_id,)).fetchone():
                    raise LedgerError("group_state_corrupt", 503)
                target = self._bind(con, account_id, device, root, other, now)
                return self._linked_reply(con, account_id, target, now)
            self._wallets(con, root['group_id'])
            if other:
                self._wallets(con, other['group_id'])
            # Bounded, on-demand cleanup; no per-user timers or workers.
            con.execute("""DELETE FROM group_confirmations WHERE digest IN (
                SELECT digest FROM group_confirmations WHERE expires_ms<=?
                ORDER BY expires_ms LIMIT 128)""", (now,))
            # Re-prepare invalidates the previous challenge for this exact pair
            # and session. It does not grow storage or authorize any new device.
            con.execute("DELETE FROM group_confirmations WHERE session_digest=? AND device_hash=?", (session, device))
            total = con.execute("SELECT COUNT(*) FROM group_confirmations").fetchone()[0]
            own = con.execute("SELECT COUNT(*) FROM group_confirmations WHERE account_id=?", (account_id,)).fetchone()[0]
            if total >= MAX_PENDING or own >= MAX_PENDING_PER_ACCOUNT:
                raise AccountError("device_confirmation_limit", 429, 300)
            challenge = 'gc1_' + secrets.token_urlsafe(32)
            digest = _opaque_digest(challenge, 'gc1_')
            expires = now + CONFIRMATION_MS
            con.execute("INSERT INTO group_confirmations VALUES(?,?,?,?,?,?,?,'pending')",
                        (digest, session, account_id, device,
                         self._scope_signature(root, other), now, expires))
            return {'status': 'confirmation_required', 'confirmation_token': challenge,
                    'expires_at_ms': expires, **_NOTICE}

    def _confirmation(self, con, token, android_id, challenge, now):
        account_id, session, device = self._actor(con, token, android_id, now)
        digest = _opaque_digest(challenge, 'gc1_')
        row = con.execute("SELECT * FROM group_confirmations WHERE digest=?", (digest,)).fetchone() if digest else None
        if row is None or row['session_digest'] != session or row['account_id'] != account_id or row['device_hash'] != device:
            raise LedgerError("invalid_device_confirmation", 403)
        if now < row['created_ms'] or now >= row['expires_ms']:
            raise LedgerError("device_confirmation_expired", 409)
        return account_id, device, row

    def cancel(self, token, android_id, challenge):
        with self.transaction() as con:
            now = self._now()
            _, _, row = self._confirmation(con, token, android_id, challenge, now)
            if row['state'] == 'confirmed':
                raise LedgerError("device_already_linked", 409)
            con.execute("UPDATE group_confirmations SET state='cancelled' WHERE digest=?", (row['digest'],))
            # No wallet reads/recovery, group edits, session revocations or grants.
            return {'status': 'cancelled'}

    def confirm(self, token, android_id, challenge):
        stale = False
        with self.transaction() as con:
            now = self._now()
            account_id, device, row = self._confirmation(con, token, android_id, challenge, now)
            if row['state'] in ('cancelled', 'stale'):
                raise LedgerError('device_confirmation_' + row['state'], 409)
            _, root, other, linked = self._scope(con, account_id, device)
            if row['state'] == 'confirmed':
                if not linked:
                    raise LedgerError("group_state_corrupt", 503)
                return self._linked_reply(con, account_id, root['group_id'], now, replayed=True)
            if self._scope_signature(root, other) != row['scope_json']:
                con.execute("UPDATE group_confirmations SET state='stale' WHERE digest=?", (row['digest'],))
                stale = True
            else:
                if linked:
                    raise LedgerError("group_state_corrupt", 503)
                target = self._bind(con, account_id, device, root, other, now)
                con.execute("UPDATE group_confirmations SET state='confirmed' WHERE digest=?", (row['digest'],))
                result = self._linked_reply(con, account_id, target, now)
        # Commit the stale state but never silently apply a larger union.
        if stale:
            raise LedgerError("device_confirmation_stale", 409)
        return result

    def authorize_in_transaction(self, con, token, android_id):
        """Final gate for FREE evaluations; no account/group IDs from the client."""
        AccountLedger._require_transaction(con)
        now = self._now()
        account_id, _, device = self._actor(con, token, android_id, now)
        _, root, _, linked = self._scope(con, account_id, device)
        if not linked:
            raise LedgerError("device_confirmation_required", 409)
        self._wallets(con, root['group_id'])
        return account_id, root['group_id']

    def _update(self, con, account_id, root, route, now, *, debit):
        route = AccountLedger._route(route)
        old_debt, old_anchor, revision = self._wallets(con, root)[route]
        anchor = max(now, old_anchor)
        debt = max(0, old_debt - (anchor - old_anchor))
        status = 'balance'
        if debit:
            if CAPACITIES[route] * HOUR_MS - debt < HOUR_MS:
                status = 'empty'
            else:
                debt += HOUR_MS
                status = 'charged'
        if (debt, anchor) != (old_debt, old_anchor):
            revision += 1
            AccountLedger._validate_row(debt, anchor, revision)
            con.execute("UPDATE group_hearts SET debt_ms=?,anchor_ms=?,revision=? WHERE group_id=? AND route=?",
                        (debt, anchor, revision, root, route))
        return {**AccountLedger._reply(account_id, route, debt, anchor, revision, status), 'group_id': root}

    def snapshot(self, token, android_id, route):
        with self.transaction() as con:
            now = self._now()
            account_id, root = self.authorize_in_transaction(con, token, android_id)
            return self._update(con, account_id, root, route, now, debit=False)

    def debit_in_transaction(self, con, token, android_id, route):
        """Internal only: caller must store the verified evaluation and receipt.

        This primitive is NOT an evaluator and NOT idempotent on its own. The
        future evaluator must key receipts by (authenticated account, attempt),
        never by the current root, then return results only after outer commit.
        """
        AccountLedger._require_transaction(con)
        now = self._now()
        account_id, root = self.authorize_in_transaction(con, token, android_id)
        return self._update(con, account_id, root, route, now, debit=True)
