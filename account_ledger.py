"""Canonical, server-owned heart balances for authenticated accounts.

Enrollment runs inside account creation's transaction. Reading a balance never
enrolls an account or repairs missing state. The debit primitive is deliberately
transaction-only: a future authoritative evaluator must record the attempt and
its result in that same transaction before returning it to Android.
"""
from __future__ import annotations

import sqlite3


HOUR_MS = 3_600_000
CAPACITIES = {"programming": 8, "math_physics": 12}
_MAX_SQLITE_INTEGER = (1 << 63) - 1


class LedgerError(Exception):
    def __init__(self, code: str, status: int = 409):
        super().__init__(code)
        self.code, self.status = code, status


def _identifier(value: object, code: str) -> str:
    # The identifier comes from authenticated server-side account resolution,
    # never a requested username or a client-provided device identifier.
    if type(value) is not str or not 1 <= len(value) <= 128 or "\x00" in value:
        raise LedgerError(code, 422)
    return value


def _integer(value: object, *, minimum: int = 0) -> bool:
    # bool is intentionally rejected even though it subclasses int in Python.
    return type(value) is int and minimum <= value <= _MAX_SQLITE_INTEGER


class AccountLedger:
    def __init__(self, database):
        self.database = database
        con = self.database.connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            version_exists = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='wallet_schema_version'"
            ).fetchone() is not None
            wallet_exists = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='account_hearts'"
            ).fetchone() is not None
            if not version_exists:
                if wallet_exists:
                    raise RuntimeError("Wallet schema marker missing; do not overwrite balances")
                con.execute("""CREATE TABLE wallet_schema_version(
                    version INTEGER NOT NULL,
                    CHECK(typeof(version)='integer' AND version=1))""")
                con.execute("INSERT INTO wallet_schema_version(version) VALUES(1)")
                con.execute("""CREATE TABLE account_hearts(
                    uid TEXT NOT NULL,
                    route TEXT NOT NULL,
                    debt_ms INTEGER NOT NULL,
                    anchor_ms INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    PRIMARY KEY(uid,route),
                    CHECK(typeof(uid)='text' AND length(uid) BETWEEN 1 AND 128),
                    CHECK(route IN ('programming','math_physics')),
                    CHECK(typeof(debt_ms)='integer' AND debt_ms>=0),
                    CHECK(typeof(anchor_ms)='integer' AND anchor_ms>=0),
                    CHECK(typeof(revision)='integer' AND revision>0))""")
            else:
                versions = con.execute("SELECT version FROM wallet_schema_version").fetchall()
                if versions != [(1,)] or type(versions[0][0]) is not int:
                    raise RuntimeError("Unsupported wallet schema; do not overwrite balances")
                if not wallet_exists:
                    raise RuntimeError("Account wallet table missing; do not recreate balances")
                columns = con.execute("PRAGMA table_info(account_hearts)").fetchall()
                expected = [
                    ("uid", "TEXT", 1, 1), ("route", "TEXT", 1, 2),
                    ("debt_ms", "INTEGER", 1, 0), ("anchor_ms", "INTEGER", 1, 0),
                    ("revision", "INTEGER", 1, 0),
                ]
                if [(c[1], c[2].upper(), c[3], c[5]) for c in columns] != expected:
                    raise RuntimeError("Account wallet schema damaged; do not overwrite balances")
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    @staticmethod
    def _require_transaction(con: sqlite3.Connection) -> None:
        if not con.in_transaction:
            raise RuntimeError("Account ledger requires an active caller-owned transaction")

    def _now(self, now: int | None = None) -> int:
        value = self.database.clock() if now is None else now
        if not _integer(value):
            raise LedgerError("invalid_clock", 503)
        return value

    @staticmethod
    def _route(route: object) -> str:
        if type(route) is not str or route not in CAPACITIES:
            raise LedgerError("unknown_route", 422)
        return route

    @staticmethod
    def _validate_row(debt: object, anchor: object, revision: object) -> None:
        if not (_integer(debt) and _integer(anchor) and _integer(revision, minimum=1)):
            raise LedgerError("wallet_state_corrupt", 503)

    def enroll(self, con: sqlite3.Connection, account_id: str,
               legacy_uid: str | None, now: int) -> None:
        """Give both initial balances exactly once during account creation.

        A legacy account is migrated without duplicating an old account snapshot
        already inherited by device wallets. Each device debt is normalized at
        its own anchor before debts are added; summed debt may exceed capacity.
        The caller owns commit/rollback, including account/invitation changes.
        """
        self._require_transaction(con)
        account_id = _identifier(account_id, "invalid_account_id")
        if legacy_uid is not None:
            legacy_uid = _identifier(legacy_uid, "invalid_legacy_uid")
        if not _integer(now):
            raise LedgerError("invalid_clock", 503)
        if con.execute("SELECT 1 FROM account_hearts WHERE uid=? LIMIT 1",
                       (account_id,)).fetchone() is not None:
            # A partial wallet is damaged state, not a new enrollment.
            raise LedgerError("wallet_already_enrolled", 409)

        prepared = []
        for route, cap in CAPACITIES.items():
            previous = []
            if legacy_uid is not None:
                previous = con.execute(
                    "SELECT credit_ms,anchor_ms,revision FROM device_hearts "
                    "WHERE uid=? AND route=?", (legacy_uid, route)
                ).fetchall()
                if not previous:
                    previous = con.execute(
                        "SELECT credit_ms,anchor_ms,revision FROM hearts WHERE uid=? AND route=?",
                        (legacy_uid, route)
                    ).fetchall()
            debt, anchor, revision = 0, now, 1
            for credit, old_anchor, old_revision in previous:
                self._validate_row(credit, old_anchor, old_revision)
                recovered = min(cap * HOUR_MS, credit + max(0, now - old_anchor))
                debt += cap * HOUR_MS - recovered
                anchor = max(anchor, old_anchor)
                revision = max(revision, old_revision + 1)
            self._validate_row(debt, anchor, revision)
            prepared.append((account_id, route, debt, anchor, revision))

        # A savepoint also leaves no half-enrolled wallet if a caller catches a
        # callback error before rolling back its larger account transaction.
        con.execute("SAVEPOINT account_ledger_enroll")
        try:
            con.executemany(
                "INSERT INTO account_hearts(uid,route,debt_ms,anchor_ms,revision) VALUES(?,?,?,?,?)",
                prepared,
            )
            if legacy_uid is not None and legacy_uid != account_id:
                con.execute(
                    "INSERT INTO completions(uid,kind,course,item,completed_ms) "
                    "SELECT ?,kind,course,item,completed_ms FROM completions WHERE uid=?",
                    (account_id, legacy_uid),
                )
                con.execute(
                    "INSERT INTO portable_settings(uid,namespace,values_json,revision,updated_ms) "
                    "SELECT ?,namespace,values_json,revision,updated_ms "
                    "FROM portable_settings WHERE uid=?", (account_id, legacy_uid),
                )
            con.execute("RELEASE SAVEPOINT account_ledger_enroll")
        except Exception:
            con.execute("ROLLBACK TO SAVEPOINT account_ledger_enroll")
            con.execute("RELEASE SAVEPOINT account_ledger_enroll")
            raise

    def _wallets(self, con: sqlite3.Connection, account_id: str) -> dict:
        rows = con.execute(
            "SELECT route,debt_ms,anchor_ms,revision FROM account_hearts WHERE uid=?",
            (account_id,),
        ).fetchall()
        if len(rows) != len(CAPACITIES):
            raise LedgerError("wallet_state_missing" if len(rows) < len(CAPACITIES)
                              else "wallet_state_corrupt", 503)
        wallets = {}
        for route, debt, anchor, revision in rows:
            if type(route) is not str or route not in CAPACITIES or route in wallets:
                raise LedgerError("wallet_state_corrupt", 503)
            self._validate_row(debt, anchor, revision)
            wallets[route] = (debt, anchor, revision)
        if set(wallets) != set(CAPACITIES):
            raise LedgerError("wallet_state_corrupt", 503)
        return wallets

    @staticmethod
    def _reply(account_id: str, route: str, debt: int, anchor: int,
               revision: int, status: str) -> dict:
        cap = CAPACITIES[route]
        available = max(0, cap * HOUR_MS - debt) // HOUR_MS
        return {
            "status": status,
            "replayed": False,
            "account_id": account_id,
            "route": route,
            "available": available,
            "maximum": cap,
            "server_time_ms": anchor,
            "revision": revision,
            "next_heart_at_ms": None if debt == 0 else
                anchor + debt - (cap - (available + 1)) * HOUR_MS,
        }

    def _update(self, con: sqlite3.Connection, account_id: str, route: str,
                now: int, *, debit: bool) -> dict:
        old_debt, old_anchor, revision = self._wallets(con, account_id)[route]
        anchor = max(now, old_anchor)  # A clock rollback never grants recovery.
        debt = max(0, old_debt - (anchor - old_anchor))
        status = "balance"
        if debit:
            if CAPACITIES[route] * HOUR_MS - debt < HOUR_MS:
                status = "empty"
            else:
                debt += HOUR_MS
                status = "charged"
        if (debt, anchor) != (old_debt, old_anchor):
            revision += 1
            self._validate_row(debt, anchor, revision)
            updated = con.execute(
                "UPDATE account_hearts SET debt_ms=?,anchor_ms=?,revision=? WHERE uid=? AND route=?",
                (debt, anchor, revision, account_id, route),
            )
            if updated.rowcount != 1:
                raise LedgerError("wallet_state_corrupt", 503)
        return self._reply(account_id, route, debt, anchor, revision, status)

    def snapshot(self, account_id: str, route: str) -> dict:
        """Read and lazily recover an existing account's balance; never grant."""
        account_id = _identifier(account_id, "invalid_account_id")
        route = self._route(route)
        con = self.database.connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            reply = self._update(con, account_id, route, self._now(), debit=False)
            con.commit()
            return reply
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def debit_in_transaction(self, con: sqlite3.Connection, account_id: str,
                             route: str, now: int | None = None) -> dict:
        """Internal primitive for the future authoritative evaluator only.

        Does not verify answers, record attempt IDs, or commit. Its caller must
        ensure idempotency and save evaluation and debit together in a write
        transaction. It must never be exposed as a client-directed debit API.
        """
        self._require_transaction(con)
        account_id = _identifier(account_id, "invalid_account_id")
        route = self._route(route)
        return self._update(con, account_id, route, self._now(now), debit=True)
