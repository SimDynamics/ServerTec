"""Isolated reference model for Android's offline heart wallet, not a live API.

No timers, network access, default data directory, Premium decisions, or server
reconciliation. Android must supply elapsedRealtime(), a stable boot marker and
wall time. The last one is only an UNVERIFIED fallback across boots; it is not
proof of elapsed time. Do not send these receipts to the current /v1 API without
first defining reconciliation. Production server tables are never used here.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
import sqlite3
from types import MappingProxyType
from uuid import UUID

HOUR_MS = 3_600_000
MAX_INT = 2**63 - 1
CAPACITIES = MappingProxyType({"programming": 8, "math_physics": 12})
APPLICATION_ID = 0x4C475057  # LGPW, distinct from the production ServerTec database


class RestoreRequired(ValueError):
    """Local state is absent: a verified restoration is needed, not free hearts."""


class WalletConflict(ValueError):
    """An old receipt or an existing wallet must not be overwritten."""


def _integer(value: int, upper: int = MAX_INT) -> None:
    if type(value) is not int or not 0 <= value <= upper:
        raise ValueError("invalid_nonnegative_integer")


def _identifier(value: str) -> None:
    if type(value) is not str or not 1 <= len(value) <= 128 or "\x00" in value:
        raise ValueError("invalid_identifier")


@dataclass(frozen=True)
class ClockSample:
    elapsed_ms: int
    wall_ms: int
    boot_id: str | None

    def __post_init__(self):
        _integer(self.elapsed_ms)
        _integer(self.wall_ms)
        if self.boot_id is not None:
            _identifier(self.boot_id)


@dataclass(frozen=True)
class Scope:
    account: str
    device: str
    route: str

    def __post_init__(self):
        _identifier(self.account)
        _identifier(self.device)
        if self.route not in CAPACITIES:
            raise ValueError("unknown_route")

    def key(self) -> tuple[str, str, str]:
        return self.account, self.device, self.route


@dataclass(frozen=True)
class HeartState:
    route: str
    credit_ms: int
    elapsed_anchor_ms: int
    wall_floor_ms: int
    boot_id: str | None
    used_wall_estimate: bool = False
    clock_anomaly: bool = False

    def __post_init__(self):
        if self.route not in CAPACITIES:
            raise ValueError("unknown_route")
        _integer(self.credit_ms, CAPACITIES[self.route] * HOUR_MS)
        _integer(self.elapsed_anchor_ms)
        _integer(self.wall_floor_ms)
        if self.boot_id is not None:
            _identifier(self.boot_id)
        if type(self.used_wall_estimate) is not bool or type(self.clock_anomaly) is not bool:
            raise ValueError("invalid_clock_flags")

    @property
    def available(self) -> int:
        return self.credit_ms // HOUR_MS

    @property
    def next_heart_in_ms(self) -> int | None:
        if self.credit_ms == CAPACITIES[self.route] * HOUR_MS:
            return None
        return HOUR_MS - self.credit_ms % HOUR_MS


def restored_state(route: str, credit_ms: int, sample: ClockSample) -> HeartState:
    """Adapter-only bootstrap from verified state; never a local default grant."""
    return HeartState(route, credit_ms, sample.elapsed_ms, sample.wall_ms, sample.boot_id)


@dataclass(frozen=True)
class Projection:
    state: HeartState
    clock_basis: str


def advance(state: HeartState, sample: ClockSample) -> Projection:
    """Pure O(1) lazy recovery, including at zero, with no I/O or timer jobs.

    Ignore wall-clock changes within a known boot. Across boots, use positive
    wall-time differences and mark them unverified, as the user accepted. A
    high-water mark prevents repeatedly crediting the same wall-time interval.
    Discard excess time at capacity rather than banking future free hearts.
    """
    same_boot = state.boot_id is not None and state.boot_id == sample.boot_id
    anomaly = state.clock_anomaly
    estimated = state.used_wall_estimate
    if same_boot:
        delta = max(0, sample.elapsed_ms - state.elapsed_anchor_ms)
        elapsed_anchor = max(state.elapsed_anchor_ms, sample.elapsed_ms)
        anomaly |= sample.elapsed_ms < state.elapsed_anchor_ms
        basis = "elapsed_realtime" if sample.elapsed_ms >= state.elapsed_anchor_ms else "elapsed_regressed"
        wall_floor = max(sample.wall_ms, min(MAX_INT, state.wall_floor_ms + delta))
    else:
        delta = max(0, sample.wall_ms - state.wall_floor_ms)
        elapsed_anchor = sample.elapsed_ms
        estimated = True
        anomaly |= sample.wall_ms < state.wall_floor_ms
        wall_floor = max(state.wall_floor_ms, sample.wall_ms)
        basis = "wall_estimate"
    room = CAPACITIES[state.route] * HOUR_MS - state.credit_ms
    return Projection(replace(
        state, credit_ms=state.credit_ms + min(room, delta),
        elapsed_anchor_ms=elapsed_anchor, wall_floor_ms=wall_floor,
        boot_id=sample.boot_id, used_wall_estimate=estimated, clock_anomaly=anomaly,
    ), basis)


@dataclass(frozen=True)
class Receipt:
    sequence: int
    operation_id: str
    route: str
    status: str
    credit_after_ms: int
    sample: ClockSample
    clock_basis: str
    used_wall_estimate: bool


def _operation(value: str) -> str:
    if type(value) is not str:
        raise ValueError("invalid_operation_id")
    return str(UUID(value))


class OfflineWallet:
    """Executable persistence reference; not an Android storage adapter.

    Use an explicit disposable test path. This SQLite database has its own
    application ID and cannot open production ServerTec tables. There is no
    background worker and no read that writes a balance. Never back up this
    wallet as portable settings. Acknowledgement/reconciliation is intentionally
    absent until its contract receives independent review.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                app_id = con.execute("PRAGMA application_id").fetchone()[0]
                version = con.execute("PRAGMA user_version").fetchone()[0]
                tables = {row[0] for row in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
                if app_id == 0 and version == 0 and not tables:
                    con.execute("""CREATE TABLE wallet_state(
                        account TEXT NOT NULL, device TEXT NOT NULL, route TEXT NOT NULL,
                        state_json TEXT NOT NULL, PRIMARY KEY(account,device,route))""")
                    con.execute("""CREATE TABLE wallet_receipts(
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        account TEXT NOT NULL, device TEXT NOT NULL, route TEXT NOT NULL,
                        operation_id TEXT NOT NULL, status TEXT NOT NULL,
                        credit_after_ms INTEGER NOT NULL, sample_json TEXT NOT NULL,
                        clock_basis TEXT NOT NULL, used_wall_estimate INTEGER NOT NULL,
                        UNIQUE(account,device,operation_id))""")
                    con.execute(f"PRAGMA application_id={APPLICATION_ID}")
                    con.execute("PRAGMA user_version=1")
                elif app_id != APPLICATION_ID or version != 1 or tables != {"wallet_state", "wallet_receipts"}:
                    raise ValueError("not_an_offline_wallet_database")
                con.commit()
            except BaseException:
                con.rollback()
                raise

    @contextmanager
    def _connection(self):
        with closing(sqlite3.connect(self.path, timeout=10, isolation_level=None)) as con:
            con.execute("PRAGMA synchronous=FULL")
            con.execute("PRAGMA foreign_keys=ON")
            yield con

    @contextmanager
    def _transaction(self):
        with self._connection() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                yield con
                con.commit()
            except BaseException:
                con.rollback()
                raise

    @staticmethod
    def _load(con, scope: Scope) -> HeartState:
        row = con.execute("SELECT state_json FROM wallet_state WHERE account=? AND device=? AND route=?",
                          scope.key()).fetchone()
        if row is None:
            raise RestoreRequired("restore_from_verified_source_required")
        state = HeartState(**json.loads(row[0]))
        if state.route != scope.route:
            raise ValueError("local_state_route_mismatch")
        return state

    @staticmethod
    def _save(con, scope: Scope, state: HeartState) -> None:
        con.execute("UPDATE wallet_state SET state_json=? WHERE account=? AND device=? AND route=?",
                    (json.dumps(asdict(state), sort_keys=True), *scope.key()))

    def seed_confirmed(self, scope: Scope, credit_ms: int, sample: ClockSample) -> None:
        """Caller must already have verified a server restoration; cannot replace local state."""
        state = restored_state(scope.route, credit_ms, sample)
        with self._transaction() as con:
            existing = con.execute("SELECT 1 FROM wallet_state WHERE account=? AND device=? AND route=?",
                                   scope.key()).fetchone()
            if existing:
                raise WalletConflict("existing_wallet_must_be_reconciled_not_replaced")
            con.execute("INSERT INTO wallet_state VALUES(?,?,?,?)",
                        (*scope.key(), json.dumps(asdict(state), sort_keys=True)))

    def snapshot(self, scope: Scope) -> HeartState:
        with self._connection() as con:
            return self._load(con, scope)

    def view(self, scope: Scope, sample: ClockSample) -> Projection:
        return advance(self.snapshot(scope), sample)

    def checkpoint(self, scope: Scope, sample: ClockSample) -> HeartState:
        with self._transaction() as con:
            state = advance(self._load(con, scope), sample).state
            self._save(con, scope, state)
            return state

    @staticmethod
    def _receipt(row) -> Receipt:
        seq, op, route, status, credit, sample, basis, estimated = row
        return Receipt(seq, op, route, status, credit, ClockSample(**json.loads(sample)), basis, bool(estimated))

    def lose_heart(self, scope: Scope, operation_id: str, sample: ClockSample) -> Receipt:
        """Atomically store the debit AND pending receipt before returning a result.

        Correct answers and verified Premium bypass this function in the future
        Android adapter. Replays return the original receipt, NOT current balance;
        callers must use view() for current UI state.
        """
        op = _operation(operation_id)
        with self._transaction() as con:
            prior = con.execute("""SELECT sequence,operation_id,route,status,credit_after_ms,
                sample_json,clock_basis,used_wall_estimate FROM wallet_receipts
                WHERE account=? AND device=? AND operation_id=?""",
                (scope.account, scope.device, op)).fetchone()
            if prior:
                receipt = self._receipt(prior)
                if receipt.route != scope.route:
                    raise WalletConflict("operation_id_reused_for_another_route")
                return receipt
            projection = advance(self._load(con, scope), sample)
            state = projection.state
            status = "charged" if state.credit_ms >= HOUR_MS else "empty"
            if status == "charged":
                state = replace(state, credit_ms=state.credit_ms - HOUR_MS)
            self._save(con, scope, state)
            cursor = con.execute("""INSERT INTO wallet_receipts(
                account,device,route,operation_id,status,credit_after_ms,sample_json,
                clock_basis,used_wall_estimate) VALUES(?,?,?,?,?,?,?,?,?)""",
                (*scope.key(), op, status, state.credit_ms, json.dumps(asdict(sample), sort_keys=True),
                 projection.clock_basis, int(state.used_wall_estimate)))
            return Receipt(cursor.lastrowid, op, scope.route, status, state.credit_ms,
                           sample, projection.clock_basis, state.used_wall_estimate)

    def pending_debits(self, scope: Scope, limit: int = 128) -> tuple[Receipt, ...]:
        """Read only. No transport or acknowledgement implementation in this step."""
        _integer(limit, 1024)
        if limit == 0:
            raise ValueError("batch_limit_must_be_positive")
        with self._connection() as con:
            rows = con.execute("""SELECT sequence,operation_id,route,status,credit_after_ms,
                sample_json,clock_basis,used_wall_estimate FROM wallet_receipts
                WHERE account=? AND device=? AND route=? AND status='charged'
                ORDER BY sequence LIMIT ?""", (*scope.key(), limit)).fetchall()
            return tuple(self._receipt(row) for row in rows)
