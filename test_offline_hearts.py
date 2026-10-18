"""Offline rules, durability and cross-boot edge cases without devices or servers."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
from pathlib import Path
import random
import sqlite3
import subprocess
import sys
from uuid import uuid4

import pytest

from offline_hearts import (
    APPLICATION_ID, CAPACITIES, HOUR_MS as H, MAX_INT, ClockSample, HeartState,
    OfflineWallet, RestoreRequired, Scope, WalletConflict, advance, restored_state,
)

WALL = 1_800_000_000_000


def clock(delta=0, *, boot='boot-1', wall=None, elapsed=None):
    return ClockSample(10_000 + delta if elapsed is None else elapsed,
                       WALL + delta if wall is None else wall, boot)


@pytest.fixture
def wallet(tmp_path):
    store = OfflineWallet(tmp_path / 'client-wallet.db')
    scope = Scope('student', 'device-a', 'programming')
    store.seed_confirmed(scope, 8 * H, clock())
    return store, scope


@pytest.mark.parametrize('route', list(CAPACITIES))
@pytest.mark.parametrize('delta,available,remainder', [
    (0, 0, H), (H - 1, 0, 1), (H, 1, H), (H + 1, 1, H - 1),
    (H + H // 2, 1, H // 2), (3 * H, 3, H),
])
def test_recovers_offline_from_zero_without_a_server(route, delta, available, remainder):
    state = restored_state(route, 0, clock())
    result = advance(state, clock(delta))
    assert result.state.available == available
    assert result.state.next_heart_in_ms == remainder
    assert result.clock_basis == 'elapsed_realtime'
    assert not result.state.used_wall_estimate


@pytest.mark.parametrize('route', list(CAPACITIES))
def test_capacity_is_preserved_and_excess_time_is_discarded(route, tmp_path):
    store = OfflineWallet(tmp_path / 'wallet.db')
    scope = Scope('u', 'd', route)
    cap = CAPACITIES[route]
    store.seed_confirmed(scope, cap * H, clock())
    receipt = store.lose_heart(scope, str(uuid4()), clock(1000 * H))
    assert receipt.credit_after_ms == (cap - 1) * H
    state = store.view(scope, clock(1000 * H)).state
    assert state.available == cap - 1
    assert state.next_heart_in_ms == H
    assert store.view(scope, clock(1001 * H)).state.available == cap


@pytest.mark.parametrize('wall_shift', [-100 * H, -H, 0, H, 100 * H])
def test_same_boot_ignores_manual_wall_clock_changes(wall_shift):
    state = restored_state('programming', 2 * H, clock())
    result = advance(state, clock(H // 2, wall=WALL + wall_shift))
    assert result.state.credit_ms == 2 * H + H // 2
    assert not result.state.used_wall_estimate


@pytest.mark.parametrize('scenario', ['background', 'process_recreated', 'deep_sleep'])
def test_close_reopen_and_sleep_do_not_reset_recovery(wallet, scenario):
    store, scope = wallet
    store.lose_heart(scope, str(uuid4()), clock())
    reopened = OfflineWallet(store.path)
    result = reopened.view(scope, clock(H // 2)).state
    assert result.available == 7
    assert result.next_heart_in_ms == H // 2
    assert reopened.view(scope, clock(H)).state.available == 8


def test_partial_recovery_survives_another_debit(wallet):
    store, scope = wallet
    store.lose_heart(scope, str(uuid4()), clock())
    store.lose_heart(scope, str(uuid4()), clock(H // 2))
    assert store.snapshot(scope).available == 6
    assert store.snapshot(scope).next_heart_in_ms == H // 2
    assert store.view(scope, clock(H)).state.available == 7


@pytest.mark.parametrize('remaining', [0, 1, 7, 8])
def test_reboot_keeps_saved_hearts_and_pending_debits(wallet, remaining):
    store, scope = wallet
    for _ in range(8 - remaining):
        store.lose_heart(scope, str(uuid4()), clock())
    before = store.pending_debits(scope)
    restarted = OfflineWallet(store.path)
    result = restarted.checkpoint(scope, clock(boot='boot-2', elapsed=20))
    assert result.available == remaining
    assert result.used_wall_estimate
    assert restarted.pending_debits(scope) == before


@pytest.mark.parametrize('new_elapsed', [20, 10_000 + 10 * H])
def test_reboot_uses_explicit_boot_marker_even_when_new_uptime_is_larger(new_elapsed):
    state = restored_state('programming', H, clock())
    result = advance(state, clock(2 * H, boot='boot-2', elapsed=new_elapsed))
    assert result.state.available == 3
    assert result.clock_basis == 'wall_estimate'
    assert result.state.used_wall_estimate
    again = advance(result.state, clock(2 * H, boot='boot-2', elapsed=new_elapsed))
    assert again.state.credit_ms == result.state.credit_ms


def test_reboot_fallback_then_returns_to_monotonic_recovery():
    state = restored_state('programming', 0, clock())
    rebooted = advance(state, clock(H, boot='boot-2', elapsed=20)).state
    assert rebooted.available == 1
    result = advance(rebooted, clock(H, boot='boot-2', elapsed=20 + H, wall=WALL - 100 * H))
    assert result.state.available == 2
    assert result.clock_basis == 'elapsed_realtime'
    assert result.state.used_wall_estimate  # provenance is not silently cleared


def test_wall_clock_fallback_is_not_falsely_claimed_secure():
    state = restored_state('programming', 0, clock())
    changed = advance(state, clock(100 * H, boot='boot-2', elapsed=20)).state
    assert changed.available == 8
    assert changed.used_wall_estimate


def test_backward_wall_fallback_never_removes_hearts_or_recredits_same_interval():
    state = restored_state('programming', 3 * H, clock())
    backward = advance(state, clock(boot=None, wall=WALL - H)).state
    assert backward.available == 3 and backward.clock_anomaly
    caught_up = advance(backward, clock(boot=None, wall=WALL)).state
    assert caught_up.available == 3
    future = advance(caught_up, clock(boot=None, wall=WALL + H)).state
    assert future.available == 4 and future.used_wall_estimate


def test_unknown_boot_marker_is_never_treated_as_trusted_monotonic_time():
    state = restored_state('programming', 0, clock(boot=None))
    result = advance(state, clock(H, boot=None))
    assert result.state.available == 1
    assert result.state.used_wall_estimate
    assert result.clock_basis == 'wall_estimate'


def test_elapsed_regression_does_not_duplicate_previously_counted_time():
    state = restored_state('programming', 2 * H, clock(H))
    backward = advance(state, clock(H // 2)).state
    assert backward.credit_ms == 2 * H and backward.clock_anomaly
    assert advance(backward, clock(H)).state.credit_ms == 2 * H
    assert advance(backward, clock(2 * H)).state.credit_ms == 3 * H


@pytest.mark.parametrize('boot', ['boot-1', 'boot-2', None])
def test_extreme_durations_saturate_without_overflow(boot):
    state = restored_state('math_physics', 0, clock())
    result = advance(state, ClockSample(MAX_INT, MAX_INT, boot)).state
    assert result.credit_ms == 12 * H
    assert result.next_heart_in_ms is None
    assert result.wall_floor_ms <= MAX_INT


@pytest.mark.parametrize('field,value', [
    ('elapsed_ms', -1), ('elapsed_ms', True), ('elapsed_ms', 1.5),
    ('wall_ms', MAX_INT + 1), ('wall_ms', False), ('boot_id', ''), ('boot_id', 2),
])
def test_invalid_clock_samples_fail_closed(field, value):
    data = asdict(clock())
    data[field] = value
    with pytest.raises(ValueError):
        ClockSample(**data)


@pytest.mark.parametrize('credit', [-1, 8 * H + 1, True, 0.5])
def test_invalid_credit_cannot_create_state(credit):
    with pytest.raises(ValueError):
        restored_state('programming', credit, clock())


def test_absent_or_deleted_wallet_never_gets_an_automatic_initial_grant(tmp_path):
    scope = Scope('u', 'd', 'programming')
    path = tmp_path / 'client.db'
    store = OfflineWallet(path)
    with pytest.raises(RestoreRequired):
        store.view(scope, clock())
    store.seed_confirmed(scope, H, clock())
    path.unlink()
    recreated = OfflineWallet(path)
    with pytest.raises(RestoreRequired):
        recreated.lose_heart(scope, str(uuid4()), clock(100 * H))
    with pytest.raises(RestoreRequired):
        recreated.view(scope, clock(100 * H))


def test_remote_restore_cannot_overwrite_pending_local_spends(wallet):
    store, scope = wallet
    store.lose_heart(scope, str(uuid4()), clock())
    with pytest.raises(WalletConflict):
        store.seed_confirmed(scope, 8 * H, clock(H))
    assert store.snapshot(scope).available == 7
    assert len(store.pending_debits(scope)) == 1


def test_replayed_receipt_is_not_reapplied_or_confused_with_current_balance(wallet):
    store, scope = wallet
    op = str(uuid4())
    receipt = store.lose_heart(scope, op, clock())
    store.lose_heart(scope, str(uuid4()), clock())
    assert store.lose_heart(scope, op.upper(), clock()) == receipt
    assert store.view(scope, clock()).state.available == 6
    assert len(store.pending_debits(scope)) == 2


def test_denied_operation_stays_denied_after_refill_without_network_pending(wallet):
    store, scope = wallet
    for _ in range(8):
        store.lose_heart(scope, str(uuid4()), clock())
    op = str(uuid4())
    denied = store.lose_heart(scope, op, clock())
    assert denied.status == 'empty'
    assert store.lose_heart(scope, op, clock(H)) == denied
    assert store.view(scope, clock(H)).state.available == 1
    assert len(store.pending_debits(scope)) == 8
    assert store.lose_heart(scope, str(uuid4()), clock(H)).status == 'charged'


def test_idempotency_is_scoped_to_account_device_and_not_another_route(wallet):
    store, scope = wallet
    op = str(uuid4())
    store.lose_heart(scope, op, clock())
    math = Scope(scope.account, scope.device, 'math_physics')
    store.seed_confirmed(math, 12 * H, clock())
    with pytest.raises(WalletConflict):
        store.lose_heart(math, op, clock())
    for other in (Scope('another', scope.device, scope.route),
                  Scope(scope.account, 'another', scope.route)):
        store.seed_confirmed(other, 8 * H, clock())
        assert store.pending_debits(other) == ()
        assert store.lose_heart(other, op, clock()).credit_after_ms == 7 * H
    assert store.snapshot(math).available == 12


def test_many_parallel_retries_charge_once(wallet):
    store, scope = wallet
    op = str(uuid4())
    with ThreadPoolExecutor(max_workers=8) as pool:
        receipts = list(pool.map(lambda _: store.lose_heart(scope, op, clock()), range(24)))
    assert len(set(receipts)) == 1
    assert store.snapshot(scope).available == 7
    assert len(store.pending_debits(scope)) == 1


def test_parallel_distinct_attempts_never_overspend(wallet):
    store, scope = wallet
    with ThreadPoolExecutor(max_workers=8) as pool:
        receipts = list(pool.map(lambda _: store.lose_heart(scope, str(uuid4()), clock()), range(24)))
    assert sum(r.status == 'charged' for r in receipts) == 8
    assert store.snapshot(scope).available == 0
    assert len(store.pending_debits(scope)) == 8


def test_failure_between_debit_and_receipt_rolls_back_both(wallet):
    store, scope = wallet
    before = store.snapshot(scope)
    with closing(sqlite3.connect(store.path)) as con:
        con.execute("""CREATE TRIGGER abort_receipt BEFORE INSERT ON wallet_receipts
                       BEGIN SELECT RAISE(ABORT, 'simulated_disk_failure'); END""")
        con.commit()
    with pytest.raises(sqlite3.IntegrityError, match='simulated_disk_failure'):
        store.lose_heart(scope, str(uuid4()), clock())
    assert store.snapshot(scope) == before
    assert store.pending_debits(scope) == ()


def test_abrupt_process_exit_between_debit_and_receipt_is_atomic(wallet):
    store, scope = wallet
    before = store.snapshot(scope)
    code = '''
import os, sys
from offline_hearts import OfflineWallet, Scope, ClockSample
class CrashingWallet(OfflineWallet):
    @staticmethod
    def _save(con, scope, state):
        OfflineWallet._save(con, scope, state)
        os._exit(37)
w = CrashingWallet(sys.argv[1])
w.lose_heart(Scope('student', 'device-a', 'programming'),
             '11111111-2222-3333-4444-555555555555',
             ClockSample(10000, 1800000000000, 'boot-1'))
'''
    child = subprocess.run([sys.executable, '-c', code, str(store.path)],
                           cwd=Path(__file__).parent, capture_output=True, timeout=20)
    assert child.returncode == 37, child.stderr.decode(errors='replace')
    reopened = OfflineWallet(store.path)
    assert reopened.snapshot(scope) == before
    assert reopened.pending_debits(scope) == ()


def test_readonly_views_do_not_write_or_generate_pending_records(wallet):
    store, scope = wallet
    store.lose_heart(scope, str(uuid4()), clock())
    before = store.path.read_bytes()
    for delta in range(0, H, 10000):
        store.view(scope, clock(delta))
    assert store.path.read_bytes() == before
    assert len(store.pending_debits(scope)) == 1


def test_database_rejects_foreign_or_future_schema_without_mutation(tmp_path):
    path = tmp_path / 'production-looking.db'
    with closing(sqlite3.connect(path)) as con:
        con.execute('CREATE TABLE hearts(sentinel TEXT)')
        con.execute("INSERT INTO hearts VALUES('KEEP_REAL_STATE')")
        con.commit()
    before = path.read_bytes()
    with pytest.raises(ValueError, match='not_an_offline_wallet_database'):
        OfflineWallet(path)
    assert path.read_bytes() == before
    fresh = OfflineWallet(tmp_path / 'future.db')
    with closing(sqlite3.connect(fresh.path)) as con:
        con.execute('PRAGMA user_version=999')
        con.commit()
    before_future = fresh.path.read_bytes()
    with pytest.raises(ValueError):
        OfflineWallet(fresh.path)
    assert fresh.path.read_bytes() == before_future


def test_corrupt_local_snapshot_is_not_replaced_by_free_hearts(wallet):
    store, scope = wallet
    with closing(sqlite3.connect(store.path)) as con:
        con.execute("UPDATE wallet_state SET state_json='not-json'")
        con.commit()
    with pytest.raises(ValueError):
        store.view(scope, clock())
    assert store.pending_debits(scope) == ()


def test_every_sqlite_handle_is_explicitly_closed(tmp_path, monkeypatch):
    import offline_hearts
    retained = []
    original = sqlite3.connect

    class Tracked(sqlite3.Connection):
        was_closed = False
        def close(self):
            super().close()
            self.was_closed = True

    def tracked(*args, **kwargs):
        result = original(*args, factory=Tracked, **kwargs)
        retained.append(result)
        return result

    monkeypatch.setattr(offline_hearts.sqlite3, 'connect', tracked)
    path = tmp_path / 'wallet.db'
    store = OfflineWallet(path)
    scope = Scope('u', 'd', 'programming')
    with pytest.raises(RestoreRequired):
        store.snapshot(scope)
    store.seed_confirmed(scope, 8 * H, clock())
    store.lose_heart(scope, str(uuid4()), clock())
    store.view(scope, clock(H))
    store.pending_debits(scope)
    store.checkpoint(scope, clock(H))
    assert retained and all(c.was_closed for c in retained)
    path.unlink()


@pytest.mark.parametrize('route', list(CAPACITIES))
def test_random_sequences_match_independent_fixed_point_accounting(tmp_path, route):
    rng = random.Random(417)
    scope = Scope('u', 'd', route)
    store = OfflineWallet(tmp_path / 'wallet.db')
    cap = CAPACITIES[route] * H
    store.seed_confirmed(scope, cap, clock())
    credit, elapsed, charged = cap, 0, 0
    for _ in range(1000):
        delta = rng.randrange(0, 2 * H)
        elapsed += delta
        credit = min(cap, credit + delta)
        if credit >= H:
            credit -= H
            charged += 1
        result = store.lose_heart(scope, str(uuid4()), clock(elapsed, wall=WALL + rng.randrange(-H, H)))
        assert result.credit_after_ms == credit
        assert 0 <= store.snapshot(scope).credit_ms <= cap
    assert len(store.pending_debits(scope, limit=1024)) == charged


def test_serialized_state_preserves_flags_and_fractional_recovery():
    state = restored_state('programming', H // 2, clock())
    state = advance(state, clock(H, boot='boot-2', elapsed=42)).state
    serialized = json.dumps(asdict(state))
    assert HeartState(**json.loads(serialized)) == state


def test_pending_batches_are_bounded_ordered_and_readonly(wallet):
    store, scope = wallet
    for _ in range(5):
        store.lose_heart(scope, str(uuid4()), clock())
    first = store.pending_debits(scope, limit=2)
    assert len(first) == 2
    assert first == store.pending_debits(scope, limit=2)
    assert [r.sequence for r in first] == sorted(r.sequence for r in first)
    for invalid in (0, -1, 1025, True):
        with pytest.raises(ValueError):
            store.pending_debits(scope, limit=invalid)
