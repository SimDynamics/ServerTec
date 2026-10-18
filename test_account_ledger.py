"""Security and persistence gates for account-owned heart balances."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from account_ledger import AccountLedger, CAPACITIES, HOUR_MS, LedgerError
from servertec import Database


@pytest.fixture
def ledger(tmp_path):
    clock = [1_800_000_000_000]
    database = Database(tmp_path / "runtime" / "account-ledger.db", clock=lambda: clock[0])
    return AccountLedger(database), database, clock


def enroll(ledger, database, clock, account_id="acct_student", legacy_uid=None):
    con = database.connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        ledger.enroll(con, account_id, legacy_uid, clock[0])
        assert con.in_transaction
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def debit(ledger, database, account_id="acct_student", route="programming"):
    con = database.connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        result = ledger.debit_in_transaction(con, account_id, route)
        assert con.in_transaction
        con.commit()
        return result
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def rows(database, table, uid=None):
    assert table in {"account_hearts", "hearts", "device_hearts", "completions", "portable_settings"}
    con = database.connect()
    try:
        query = "SELECT * FROM " + table
        return con.execute(query if uid is None else query + " WHERE uid=?",
                           () if uid is None else (uid,)).fetchall()
    finally:
        con.close()


def execute(database, sql, args=()):
    con = database.connect()
    try:
        return con.execute(sql, args).rowcount
    finally:
        con.close()


def test_enrollment_is_only_grant_and_reopen_keeps_spent_hearts(ledger):
    wallet, database, clock = ledger
    with pytest.raises(LedgerError, match="wallet_state_missing"):
        wallet.snapshot("acct_student", "programming")
    assert rows(database, "account_hearts") == []
    enroll(wallet, database, clock)
    assert wallet.snapshot("acct_student", "programming")["available"] == 8
    assert wallet.snapshot("acct_student", "math_physics")["available"] == 12
    assert debit(wallet, database)["available"] == 7
    reopened = AccountLedger(Database(database.path, clock=lambda: clock[0]))
    assert reopened.snapshot("acct_student", "programming")["available"] == 7
    with pytest.raises(LedgerError, match="wallet_already_enrolled"):
        enroll(reopened, database, clock)
    assert reopened.snapshot("acct_student", "programming")["available"] == 7


def test_accounts_and_routes_have_one_server_owned_balance_each(ledger):
    wallet, database, clock = ledger
    enroll(wallet, database, clock, "acct_a")
    enroll(wallet, database, clock, "acct_b")
    debit(wallet, database, "acct_a")
    assert wallet.snapshot("acct_a", "programming")["available"] == 7
    assert wallet.snapshot("acct_a", "math_physics")["available"] == 12
    assert wallet.snapshot("acct_b", "programming")["available"] == 8
    assert len(rows(database, "account_hearts")) == 4
    assert rows(database, "device_hearts") == []


@pytest.mark.parametrize("deleted_route", ["programming", "math_physics", None])
def test_missing_wallet_never_grants_or_repairs_other_route(ledger, deleted_route):
    wallet, database, clock = ledger
    enroll(wallet, database, clock)
    debit(wallet, database)
    if deleted_route is None:
        execute(database, "DELETE FROM account_hearts WHERE uid=?", ("acct_student",))
    else:
        execute(database, "DELETE FROM account_hearts WHERE uid=? AND route=?",
                ("acct_student", deleted_route))
    before = rows(database, "account_hearts")
    for route in CAPACITIES:
        with pytest.raises(LedgerError, match="wallet_state_missing"):
            wallet.snapshot("acct_student", route)
        with pytest.raises(LedgerError, match="wallet_state_missing"):
            debit(wallet, database, route=route)
    assert rows(database, "account_hearts") == before
    if deleted_route is not None:
        with pytest.raises(LedgerError, match="wallet_already_enrolled"):
            enroll(wallet, database, clock)
        assert rows(database, "account_hearts") == before


def test_caller_rollback_discards_enrollment_and_debit(ledger):
    wallet, database, clock = ledger
    con = database.connect()
    try:
        with pytest.raises(RuntimeError, match="active caller-owned transaction"):
            wallet.enroll(con, "acct_student", None, clock[0])
        con.execute("BEGIN IMMEDIATE")
        wallet.enroll(con, "acct_student", None, clock[0])
        con.rollback()
        assert rows(database, "account_hearts") == []
        enroll(wallet, database, clock)
        with pytest.raises(RuntimeError, match="active caller-owned transaction"):
            wallet.debit_in_transaction(con, "acct_student", "programming")
        con.execute("BEGIN IMMEDIATE")
        assert wallet.debit_in_transaction(con, "acct_student", "programming")["available"] == 7
        con.rollback()
        assert wallet.snapshot("acct_student", "programming")["available"] == 8
        assert con.execute("SELECT 1").fetchone() == (1,)
    finally:
        con.close()


def test_recovery_boundaries_full_capacity_and_clock_rollback(ledger):
    wallet, database, clock = ledger
    enroll(wallet, database, clock)
    start = clock[0]
    first = debit(wallet, database)
    assert first["available"] == 7
    assert first["next_heart_at_ms"] == start + HOUR_MS
    clock[0] -= 10 * HOUR_MS
    rolled_back = wallet.snapshot("acct_student", "programming")
    assert rolled_back["server_time_ms"] == start
    assert rolled_back["available"] == 7
    assert rolled_back["next_heart_at_ms"] == start + HOUR_MS
    clock[0] = start + HOUR_MS - 1
    almost = wallet.snapshot("acct_student", "programming")
    assert almost["available"] == 7
    assert almost["next_heart_at_ms"] == clock[0] + 1
    clock[0] += 1
    recovered = wallet.snapshot("acct_student", "programming")
    assert recovered["available"] == 8
    assert recovered["next_heart_at_ms"] is None
    clock[0] += 10000 * HOUR_MS
    assert wallet.snapshot("acct_student", "programming")["available"] == 8


def test_concurrent_debits_do_not_spend_more_than_enrolled_capacity(ledger):
    wallet, database, clock = ledger
    enroll(wallet, database, clock)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: debit(wallet, database), range(24)))
    assert sum(result["status"] == "charged" for result in results) == 8
    assert sum(result["status"] == "empty" for result in results) == 16
    assert wallet.snapshot("acct_student", "programming")["available"] == 0
    assert wallet.snapshot("acct_student", "math_physics")["available"] == 12
    before = rows(database, "account_hearts")
    assert debit(wallet, database)["status"] == "empty"
    assert rows(database, "account_hearts") == before
    clock[0] += HOUR_MS
    assert debit(wallet, database)["status"] == "charged"
    assert wallet.snapshot("acct_student", "programming")["available"] == 0


def test_concurrent_enrollment_has_only_one_winner(ledger):
    wallet, database, clock = ledger

    def attempt(_):
        try:
            enroll(wallet, database, clock)
            return "enrolled"
        except LedgerError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(attempt, range(16)))
    assert outcomes.count("enrolled") == 1
    assert outcomes.count("wallet_already_enrolled") == 15
    assert len(rows(database, "account_hearts")) == 2


def test_migration_ignores_duplicate_snapshot_and_preserves_excess_debt(ledger):
    wallet, database, clock = ledger
    for device in ("a" * 64, "b" * 64):
        execute(database, "INSERT INTO device_hearts VALUES(?,?,?,?,?,?)",
                ("legacy", device, "programming", 3 * HOUR_MS, clock[0], 4))
    execute(database, "INSERT INTO hearts VALUES(?,?,?,?,?)",
            ("legacy", "programming", 3 * HOUR_MS, clock[0], 4))
    execute(database, "INSERT INTO hearts VALUES(?,?,?,?,?)",
            ("legacy", "math_physics", 10 * HOUR_MS, clock[0], 8))
    old_devices, old_hearts = rows(database, "device_hearts"), rows(database, "hearts")
    enroll(wallet, database, clock, legacy_uid="legacy")
    state = wallet.snapshot("acct_student", "programming")
    assert state["available"] == 0
    assert state["revision"] == 5
    assert state["next_heart_at_ms"] == clock[0] + 3 * HOUR_MS
    assert wallet.snapshot("acct_student", "math_physics")["available"] == 10
    programming_row = next(row for row in rows(database, "account_hearts") if row[1] == "programming")
    assert programming_row[2] == 10 * HOUR_MS
    clock[0] += 3 * HOUR_MS - 1
    state = wallet.snapshot("acct_student", "programming")
    assert state["available"] == 0
    assert state["next_heart_at_ms"] == clock[0] + 1
    clock[0] += 1
    assert wallet.snapshot("acct_student", "programming")["available"] == 1
    assert rows(database, "device_hearts") == old_devices
    assert rows(database, "hearts") == old_hearts
    assert AccountLedger(database).snapshot("acct_student", "programming")["available"] == 1


def test_each_legacy_anchor_is_normalized_independently(ledger):
    wallet, database, clock = ledger
    start = clock[0]
    execute(database, "INSERT INTO device_hearts VALUES(?,?,?,?,?,?)",
            ("legacy", "a" * 64, "programming", 3 * HOUR_MS, start + 10 * HOUR_MS, 7))
    execute(database, "INSERT INTO device_hearts VALUES(?,?,?,?,?,?)",
            ("legacy", "b" * 64, "programming", 4 * HOUR_MS, start - 2 * HOUR_MS, 5))
    enroll(wallet, database, clock, legacy_uid="legacy")
    state = wallet.snapshot("acct_student", "programming")
    # Five unpaid hours on the future-anchored wallet plus two on the older one.
    assert state["available"] == 1
    assert state["server_time_ms"] == start + 10 * HOUR_MS
    assert state["next_heart_at_ms"] == start + 11 * HOUR_MS
    assert state["revision"] == 8
    clock[0] = start + 10 * HOUR_MS
    assert wallet.snapshot("acct_student", "programming")["available"] == 1
    clock[0] += HOUR_MS
    assert wallet.snapshot("acct_student", "programming")["available"] == 2


def test_migration_copies_completions_and_settings_without_mutating_legacy(ledger):
    wallet, database, clock = ledger
    execute(database, "INSERT INTO completions VALUES(?,?,?,?,?)",
            ("legacy", "lesson", "cpp1", "l1", clock[0] - 5000))
    execute(database, "INSERT INTO portable_settings VALUES(?,?,?,?,?)",
            ("legacy", "appearance", '{"theme":"dark"}', 9, clock[0] - 2000))
    completions = rows(database, "completions", "legacy")
    settings = rows(database, "portable_settings", "legacy")
    enroll(wallet, database, clock, legacy_uid="legacy")
    assert rows(database, "completions", "acct_student") == [("acct_student", *completions[0][1:])]
    assert rows(database, "portable_settings", "acct_student") == [("acct_student", *settings[0][1:])]
    assert rows(database, "completions", "legacy") == completions
    assert rows(database, "portable_settings", "legacy") == settings


def test_failed_progress_copy_rolls_back_wallet_and_prior_copy_inside_savepoint(ledger):
    wallet, database, clock = ledger
    execute(database, "INSERT INTO completions VALUES(?,?,?,?,?)",
            ("legacy", "lesson", "cpp1", "l1", clock[0]))
    for uid in ("legacy", "acct_student"):
        execute(database, "INSERT INTO portable_settings VALUES(?,?,?,?,?)",
                (uid, "appearance", '{"theme":"dark"}', 1, clock[0]))
    con = database.connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.IntegrityError):
            wallet.enroll(con, "acct_student", "legacy", clock[0])
        assert con.in_transaction
        # Even an accidental commit of the caller after catching this error
        # cannot leave new wallet grants or a partial progress migration.
        con.commit()
    finally:
        con.close()
    assert rows(database, "account_hearts") == []
    assert rows(database, "completions", "acct_student") == []
    assert len(rows(database, "portable_settings", "acct_student")) == 1


@pytest.mark.parametrize("account_id", [None, True, 1, [], "", "a" * 129, "x\x00y"])
def test_invalid_identifiers_fail_without_sql_coercion(ledger, account_id):
    wallet, database, clock = ledger
    with pytest.raises(LedgerError, match="invalid_account_id"):
        wallet.snapshot(account_id, "programming")
    with pytest.raises(LedgerError, match="invalid_account_id"):
        enroll(wallet, database, clock, account_id)
    assert rows(database, "account_hearts") == []


@pytest.mark.parametrize("route", [None, True, 1, [], "", "PROGRAMMING", "unknown"])
def test_unknown_routes_fail_without_mutating_wallet(ledger, route):
    wallet, database, clock = ledger
    enroll(wallet, database, clock)
    before = rows(database, "account_hearts")
    with pytest.raises(LedgerError, match="unknown_route"):
        wallet.snapshot("acct_student", route)
    with pytest.raises(LedgerError, match="unknown_route"):
        debit(wallet, database, route=route)
    assert rows(database, "account_hearts") == before


@pytest.mark.parametrize("bad_now", [True, 1.25, "1800000000000", -1, 1 << 63])
def test_clock_types_and_range_fail_closed(ledger, bad_now):
    wallet, database, clock = ledger
    enroll(wallet, database, clock)
    before = rows(database, "account_hearts")
    clock[0] = bad_now
    with pytest.raises(LedgerError, match="invalid_clock"):
        wallet.snapshot("acct_student", "programming")
    with pytest.raises(LedgerError, match="invalid_clock"):
        debit(wallet, database)
    assert rows(database, "account_hearts") == before


@pytest.mark.parametrize("column,value", [
    ("debt_ms", -1), ("debt_ms", 0.5), ("debt_ms", "broken"),
    ("anchor_ms", -1), ("anchor_ms", "broken"), ("revision", 0),
])
def test_constraints_reject_corruption_and_reads_also_fail_closed(ledger, column, value):
    wallet, database, clock = ledger
    enroll(wallet, database, clock)
    assert column in {"debt_ms", "anchor_ms", "revision"}
    sql = "UPDATE account_hearts SET " + column + "=? WHERE uid=? AND route=?"
    args = (value, "acct_student", "math_physics")
    con = database.connect()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(sql, args)
        con.execute("PRAGMA ignore_check_constraints=ON")
        con.execute(sql, args)
    finally:
        con.close()
    before = rows(database, "account_hearts")
    # Corruption of the other route blocks the whole enrolled account too.
    with pytest.raises(LedgerError, match="wallet_state_corrupt"):
        wallet.snapshot("acct_student", "programming")
    with pytest.raises(LedgerError, match="wallet_state_corrupt"):
        debit(wallet, database)
    assert rows(database, "account_hearts") == before


def test_invalid_legacy_wallet_blocks_enrollment_without_grant(ledger):
    wallet, database, clock = ledger
    execute(database, "INSERT INTO hearts VALUES(?,?,?,?,?)",
            ("legacy", "math_physics", 10 * HOUR_MS, clock[0], 0))
    with pytest.raises(LedgerError, match="wallet_state_corrupt"):
        enroll(wallet, database, clock, legacy_uid="legacy")
    assert rows(database, "account_hearts") == []


@pytest.mark.parametrize("missing", ["wallet_schema_version", "account_hearts"])
def test_missing_schema_is_rejected_without_recreation(ledger, missing):
    wallet, database, clock = ledger
    enroll(wallet, database, clock)
    assert missing in {"wallet_schema_version", "account_hearts"}
    execute(database, "DROP TABLE " + missing)
    with pytest.raises(RuntimeError, match="missing"):
        AccountLedger(database)
    con = database.connect()
    try:
        assert con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                           (missing,)).fetchone() is None
    finally:
        con.close()


def test_every_owned_connection_closes_on_success_or_failure(ledger, monkeypatch):
    wallet, database, clock = ledger
    enroll(wallet, database, clock)
    tracked = []

    class TrackedConnection(sqlite3.Connection):
        closed_explicitly = False

        def close(self):
            super().close()
            self.closed_explicitly = True

    def connect():
        con = sqlite3.connect(database.path, timeout=10, isolation_level=None,
                              factory=TrackedConnection)
        tracked.append(con)
        return con

    monkeypatch.setattr(database, "connect", connect)
    try:
        reopened = AccountLedger(database)
        reopened.snapshot("acct_student", "programming")
        with pytest.raises(LedgerError, match="wallet_state_missing"):
            reopened.snapshot("missing_account", "programming")
        clock[0] = "invalid_clock"
        with pytest.raises(LedgerError, match="invalid_clock"):
            reopened.snapshot("acct_student", "programming")
        assert tracked and all(con.closed_explicitly for con in tracked)
        execute(database, "DROP TABLE account_hearts")
        with pytest.raises(RuntimeError, match="missing"):
            AccountLedger(database)
        assert all(con.closed_explicitly for con in tracked)
    finally:
        for con in tracked:
            con.close()
