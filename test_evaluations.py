"""Atomic, account-private evaluation receipts over real disposable SQLite state.

Tiny deterministic rules isolate the transaction/receipt protocol from curriculum
parsing. The companion catalog tests cover real educational answer formats.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from uuid import uuid4

import pytest

from account_ledger import HOUR_MS as H, LedgerError
from accounts import AccountError
from evaluations import EvaluationService
from exercise_catalog import CatalogError
from test_consumption_groups import Harness, PASS, A, B


EXERCISE = 'programming/cpp1/u1/l1/choice'
OTHER_EXERCISE = 'programming/cpp1/u1/l1/other'
MATH_EXERCISE = 'math_physics/math1/u1/l1/choice'
V1, V2 = 'a' * 64, 'b' * 64


class Rule:
    def __init__(self, *, route='programming', version=V1):
        self.route, self.kind, self.version = route, 'mcq', version
        self.evaluations = 0
        self.failure = None

    def validate_answer(self, answer):
        if (type(answer) is not dict or 'choice' not in answer
                or set(answer) - {'choice', 'work'}
                or type(answer['choice']) is not int
                or not 0 <= answer['choice'] <= 1000):
            raise CatalogError('invalid_answer', 422)

    def evaluate(self, answer):
        self.evaluations += 1
        if self.failure:
            raise self.failure
        return answer['choice'] == 2


class Catalog:
    def __init__(self):
        self.rules = {
            (EXERCISE, V1): Rule(),
            (OTHER_EXERCISE, V1): Rule(),
            (MATH_EXERCISE, V1): Rule(route='math_physics'),
        }
        self.resolutions = 0
        self.forbid_resolution = False

    def resolve(self, exercise_id, version):
        self.resolutions += 1
        if self.forbid_resolution:
            raise AssertionError('a durable receipt must not need the catalog')
        try:
            return self.rules[exercise_id, version]
        except KeyError:
            raise CatalogError('exercise_not_found', 404) from None


class Rig:
    def __init__(self, state):
        self.h = Harness(state)
        self.account = self.h.register()
        self.h.bind(self.account, A)
        self.catalog = Catalog()
        self.service = EvaluationService(self.h.groups, self.catalog)

    def send(self, answer, *, attempt=None, account=None, device=A,
             exercise=EXERCISE, version=V1):
        who = self.account if account is None else account
        return self.service.evaluate(who['access_token'], device,
            str(uuid4()) if attempt is None else attempt, exercise, version, answer)

    @property
    def rule(self):
        return self.catalog.rules[EXERCISE, V1]

    def empty(self, route='programming', *, account=None, device=A):
        who = self.account if account is None else account
        while self.h.balance(who, device, route)['available']:
            assert self.h.debit(who, device, route)['status'] == 'charged'

    def state(self):
        return self.h.dump([
            'group_hearts', 'consumption_groups', 'group_accounts',
            'group_account_devices', 'evaluation_results', 'evaluation_attempts',
            'auth_accounts', 'completions', 'portable_settings',
        ])


@pytest.fixture
def r(tmp_path):
    return Rig(tmp_path / 'state')


def fails(code, action, status=None):
    with pytest.raises((LedgerError, AccountError, CatalogError)) as caught:
        action()
    assert caught.value.code == code
    if status is not None:
        assert caught.value.status == status
    return caught.value


def assert_receipt(reply, attempt, *, correct, charged, duplicate=False):
    assert reply['status'] == 'evaluated'
    receipt = reply['receipt']
    assert receipt['attempt_id'] == attempt
    assert receipt['exercise_id'] == EXERCISE
    assert receipt['exercise_version'] == V1
    assert receipt['correct'] is correct
    assert type(receipt['charged_hearts']) is int
    assert receipt['charged_hearts'] == charged
    assert receipt['duplicate_answer'] is duplicate
    assert type(receipt['evaluated_at_ms']) is int
    assert type(receipt['confirmed_at_ms']) is int
    assert receipt['confirmed_at_ms'] >= receipt['evaluated_at_ms']
    assert reply['hearts']['route'] == 'programming'
    return receipt


@pytest.mark.parametrize('choice,correct,charged,remaining', [
    (2, True, 0, 8), (0, False, 1, 7),
])
def test_verified_result_and_debit_produce_one_durable_receipt(r, choice, correct, charged, remaining):
    attempt = str(uuid4())
    reply = r.send({'choice': choice}, attempt=attempt)
    assert reply['replayed'] is False
    assert_receipt(reply, attempt, correct=correct, charged=charged)
    assert reply['hearts']['available'] == remaining
    assert r.h.balance(r.account)['available'] == remaining
    assert r.rule.evaluations == 1
    with closing(r.h.db.connect()) as con:
        assert con.execute('SELECT COUNT(*) FROM evaluation_results').fetchone()[0] == 1
        assert con.execute('SELECT COUNT(*) FROM evaluation_attempts').fetchone()[0] == 1


def test_lost_response_replays_historical_charge_without_charging_again(r):
    attempt = str(uuid4())
    first = r.send({'choice': 0}, attempt=attempt)
    before = r.state()
    for _ in range(4):
        replay = r.send({'choice': 0}, attempt=attempt)
        assert replay['replayed'] is True
        assert replay['receipt'] == first['receipt']
        assert replay['receipt']['charged_hearts'] == 1
        assert replay['hearts']['available'] == 7
    assert r.rule.evaluations == 1
    assert r.state() == before


def test_replay_returns_current_hearts_and_unchanged_historical_receipt(r):
    attempt = str(uuid4())
    first = r.send({'choice': 0}, attempt=attempt)
    r.h.debit(r.account)
    replay = r.send({'choice': 0}, attempt=attempt)
    assert replay['hearts']['available'] == 6
    assert replay['receipt'] == first['receipt']
    r.h.time[0] += H
    replay = r.send({'choice': 0}, attempt=attempt)
    assert replay['hearts']['available'] == 7
    assert replay['receipt'] == first['receipt']
    assert r.rule.evaluations == 1


@pytest.mark.parametrize('changed', ['answer', 'exercise', 'version'])
@pytest.mark.parametrize('initially_empty', [False, True])
def test_attempt_identifier_cannot_be_reassigned_after_result_or_pending(r, changed, initially_empty):
    if initially_empty:
        r.empty()
    attempt = str(uuid4())
    first = r.send({'choice': 0}, attempt=attempt)
    assert first['status'] == ('pending' if initially_empty else 'evaluated')
    before = r.state()
    params = {'answer': {'choice': 0}, 'attempt': attempt}
    if changed == 'answer':
        params['answer'] = {'choice': 1}
    elif changed == 'exercise':
        params['exercise'] = OTHER_EXERCISE
    else:
        params['version'] = V2
    fails('attempt_conflict', lambda: r.send(**params), 409)
    assert r.state() == before


def test_a_b_a_with_new_identifiers_charges_only_two_distinct_wrong_answers(r):
    ids = [str(uuid4()) for _ in range(3)]
    replies = [r.send({'choice': choice}, attempt=attempt)
               for choice, attempt in zip((0, 1, 0), ids)]
    for i in (0, 1):
        assert_receipt(replies[i], ids[i], correct=False, charged=1)
        assert replies[i]['replayed'] is False
    assert_receipt(replies[2], ids[2], correct=False, charged=0, duplicate=True)
    assert replies[2]['replayed'] is False
    assert replies[2]['receipt']['evaluated_at_ms'] == replies[0]['receipt']['evaluated_at_ms']
    assert r.rule.evaluations == 2
    assert r.h.balance(r.account)['available'] == 6
    with closing(r.h.db.connect()) as con:
        assert con.execute('SELECT COUNT(*) FROM evaluation_results').fetchone()[0] == 2
        assert con.execute('SELECT COUNT(*) FROM evaluation_attempts').fetchone()[0] == 3


def test_canonical_json_object_order_matches_without_coercing_answer_values(r):
    first = {'choice': 0, 'work': {'steps': [1, 2], 'shown': True}}
    reordered = {'work': {'shown': True, 'steps': [1, 2]}, 'choice': 0}
    a = r.send(first)
    b = r.send(reordered)
    assert b['receipt']['duplicate_answer'] is True
    assert b['receipt']['charged_hearts'] == 0
    assert b['receipt']['evaluated_at_ms'] == a['receipt']['evaluated_at_ms']
    changed = r.send({'choice': 0, 'work': {'shown': 1, 'steps': [1, 2]}})
    assert changed['receipt']['duplicate_answer'] is False
    assert changed['receipt']['charged_hearts'] == 1
    assert r.rule.evaluations == 2


def test_same_json_in_new_exercise_or_revision_is_independent(r):
    r.catalog.rules[EXERCISE, V2] = Rule(version=V2)
    first = r.send({'choice': 0})
    other = r.send({'choice': 0}, exercise=OTHER_EXERCISE)
    revised = r.send({'choice': 0}, version=V2)
    assert all(x['receipt']['charged_hearts'] == 1 for x in (first, other, revised))
    assert all(x['receipt']['duplicate_answer'] is False for x in (first, other, revised))
    assert r.h.balance(r.account)['available'] == 5


def test_identical_answer_and_attempt_are_private_between_accounts_on_shared_device(r):
    other = r.h.register()
    r.h.bind(other, A)
    attempt = str(uuid4())
    a = r.send({'choice': 0}, attempt=attempt)
    b = r.send({'choice': 0}, attempt=attempt, account=other)
    assert a['receipt']['charged_hearts'] == b['receipt']['charged_hearts'] == 1
    assert b['receipt']['duplicate_answer'] is False and b['replayed'] is False
    assert r.rule.evaluations == 2
    assert r.h.balance(r.account)['available'] == r.h.balance(other)['available'] == 6
    assert b['hearts']['account_id'] == other['account_id']
    assert r.account['account_id'] not in json.dumps(b)
    with closing(r.h.db.connect()) as con:
        assert con.execute('SELECT COUNT(DISTINCT account_id) FROM evaluation_results').fetchone()[0] == 2


def test_zero_hearts_returns_no_result_and_reserves_attempt_until_recovery(r):
    r.empty()
    attempt = str(uuid4())
    start = r.h.time[0]
    for _ in range(2):
        reply = r.send({'choice': 0}, attempt=attempt)
        assert reply['status'] == 'pending'
        assert reply['error'] == 'hearts_empty'
        assert reply['attempt_id'] == attempt
        assert reply['hearts']['available'] == 0
        assert not {'result', 'correct', 'receipt', 'solution'}.intersection(reply)
    assert r.rule.evaluations == 0
    with closing(r.h.db.connect()) as con:
        assert con.execute('SELECT COUNT(*) FROM evaluation_attempts').fetchone()[0] == 1
        assert con.execute('SELECT COUNT(*) FROM evaluation_results').fetchone()[0] == 0
    r.h.time[0] = start + H - 1
    assert r.send({'choice': 0}, attempt=attempt)['status'] == 'pending'
    r.h.time[0] += 1
    reply = r.send({'choice': 0}, attempt=attempt)
    assert_receipt(reply, attempt, correct=False, charged=1)
    assert reply['hearts']['available'] == 0
    assert reply['receipt']['evaluated_at_ms'] == r.h.time[0]
    assert reply['replayed'] is False
    assert r.send({'choice': 0}, attempt=attempt)['replayed'] is True
    assert r.rule.evaluations == 1


def test_zero_hearts_does_not_disclose_new_correct_answer(r):
    r.empty()
    reply = r.send({'choice': 2})
    assert reply['status'] == 'pending'
    assert 'receipt' not in reply and 'correct' not in reply
    assert r.rule.evaluations == 0
    assert r.h.balance(r.account)['available'] == 0


def test_prior_result_is_recoverable_with_new_id_at_zero_without_catalog(r):
    first = r.send({'choice': 0})
    r.empty()
    r.catalog.forbid_resolution = True
    attempt = str(uuid4())
    duplicate = r.send({'choice': 0}, attempt=attempt)
    assert_receipt(duplicate, attempt, correct=False, charged=0, duplicate=True)
    assert duplicate['hearts']['available'] == 0
    assert duplicate['receipt']['evaluated_at_ms'] == first['receipt']['evaluated_at_ms']
    assert r.rule.evaluations == 1
    assert r.send({'choice': 0}, attempt=attempt)['receipt'] == duplicate['receipt']


def test_pending_limit_is_bounded_per_account_and_existing_ids_can_continue(r):
    r.empty()
    attempts = [str(uuid4()) for _ in range(32)]
    for attempt in attempts:
        assert r.send({'choice': 0}, attempt=attempt)['status'] == 'pending'
    before = r.state()
    fails('pending_attempt_limit', lambda: r.send({'choice': 0}), 429)
    assert r.state() == before
    assert r.send({'choice': 0}, attempt=attempts[0])['status'] == 'pending'
    other = r.h.register()
    r.h.bind(other, A)
    assert r.send({'choice': 0}, account=other)['status'] == 'pending'
    r.h.time[0] += H
    assert r.send({'choice': 0}, attempt=attempts[0])['status'] == 'evaluated'
    assert r.send({'choice': 1})['status'] == 'pending'
    with closing(r.h.db.connect()) as con:
        assert con.execute('SELECT COUNT(*) FROM evaluation_attempts '
            'WHERE account_id=? AND result_hash IS NULL', (r.account['account_id'],)).fetchone()[0] == 32


def test_parallel_same_attempt_produces_one_charge_and_one_non_replay(r):
    attempt = str(uuid4())
    with ThreadPoolExecutor(max_workers=8) as pool:
        replies = list(pool.map(lambda _: r.send({'choice': 0}, attempt=attempt), range(24)))
    assert sum(not x['replayed'] for x in replies) == 1
    assert all(x['receipt'] == replies[0]['receipt'] for x in replies)
    assert r.rule.evaluations == 1
    assert r.h.balance(r.account)['available'] == 7


def test_parallel_same_answer_new_ids_produces_one_charge_and_durable_duplicates(r):
    attempts = [str(uuid4()) for _ in range(20)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        replies = list(pool.map(lambda attempt: r.send({'choice': 0}, attempt=attempt), attempts))
    assert sum(x['receipt']['charged_hearts'] for x in replies) == 1
    assert sum(not x['receipt']['duplicate_answer'] for x in replies) == 1
    assert all(x['replayed'] is False for x in replies)
    assert r.rule.evaluations == 1
    assert r.h.balance(r.account)['available'] == 7
    for attempt, result in zip(attempts, replies):
        assert r.send({'choice': 0}, attempt=attempt)['receipt'] == result['receipt']


def test_parallel_distinct_answers_compete_for_last_heart_without_free_verdicts(r):
    for _ in range(7):
        r.h.debit(r.account)
    attempts = [str(uuid4()) for _ in range(16)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        replies = list(pool.map(lambda item: r.send({'choice': item[0] + 10}, attempt=item[1]),
                                enumerate(attempts)))
    evaluated = [x for x in replies if x['status'] == 'evaluated']
    pending = [x for x in replies if x['status'] == 'pending']
    assert len(evaluated) == 1 and len(pending) == 15
    assert evaluated[0]['receipt']['charged_hearts'] == 1
    assert all('receipt' not in x and 'correct' not in x for x in pending)
    assert r.rule.evaluations == 1
    assert r.h.balance(r.account)['available'] == 0


def test_parallel_reuse_of_identifier_for_different_answers_has_one_winner(r):
    attempt = str(uuid4())
    def submit(choice):
        try:
            return r.send({'choice': choice}, attempt=attempt)
        except LedgerError as err:
            return err
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(submit, (0, 1)))
    successes = [x for x in replies if isinstance(x, dict)]
    failures = [x for x in replies if isinstance(x, LedgerError)]
    assert len(successes) == len(failures) == 1
    assert failures[0].code == 'attempt_conflict' and failures[0].status == 409
    assert r.rule.evaluations == 1
    assert r.h.balance(r.account)['available'] == 7


def test_receipts_and_pending_requests_survive_restart_and_new_session(r):
    done_id, pending_id = str(uuid4()), str(uuid4())
    first = r.send({'choice': 0}, attempt=done_id)
    r.empty()
    assert r.send({'choice': 1}, attempt=pending_id)['status'] == 'pending'
    r.h.enable_groups()
    r.service = EvaluationService(r.h.groups, r.catalog)
    r.h.accounts.logout(r.account['access_token'])
    r.account = r.h.accounts.login(r.account['username'], PASS, '127.0.0.1')
    r.catalog.forbid_resolution = True
    assert r.send({'choice': 0}, attempt=done_id)['receipt'] == first['receipt']
    r.catalog.forbid_resolution = False
    r.h.time[0] += H
    final = r.send({'choice': 1}, attempt=pending_id)
    assert final['receipt']['charged_hearts'] == 1
    assert r.h.balance(r.account)['available'] == 0


def test_receipts_survive_absorbed_group_and_show_current_shared_balance(r):
    other = r.h.register()
    r.h.bind(other, B)
    a_id, b_id = str(uuid4()), str(uuid4())
    first_a = r.send({'choice': 0}, attempt=a_id)
    first_b = r.send({'choice': 0}, attempt=b_id, account=other, device=B)
    r.h.bind(r.account, B)
    r.catalog.forbid_resolution = True
    replay_a = r.send({'choice': 0}, attempt=a_id)
    replay_b = r.send({'choice': 0}, attempt=b_id, account=other, device=B)
    assert replay_a['receipt'] == first_a['receipt']
    assert replay_b['receipt'] == first_b['receipt']
    assert replay_a['hearts']['available'] == replay_b['hearts']['available'] == 6
    assert replay_a['hearts']['group_id'] == replay_b['hearts']['group_id']
    assert r.rule.evaluations == 2


@pytest.mark.parametrize('gate', ['logout', 'disable', 'recover', 'unconfirmed_device'])
def test_existing_receipt_still_requires_current_account_and_device_authorization(r, gate):
    attempt = str(uuid4())
    r.send({'choice': 0}, attempt=attempt)
    device = A
    if gate == 'logout':
        r.h.accounts.logout(r.account['access_token'])
    elif gate == 'disable':
        r.h.accounts.disable_account(r.account['account_id'])
    elif gate == 'recover':
        r.h.accounts.recover(r.account['username'], r.account['recovery_code'],
                             'Replacement private test password', '127.0.0.1')
    else:
        device = B
    before = r.state()
    r.catalog.forbid_resolution = True
    expected = 'device_confirmation_required' if gate == 'unconfirmed_device' else 'invalid_credentials'
    fails(expected, lambda: r.send({'choice': 0}, attempt=attempt, device=device))
    assert r.state() == before


def test_authentication_precedes_catalog_lookup(r):
    r.h.accounts.logout(r.account['access_token'])
    r.catalog.forbid_resolution = True
    fails('invalid_credentials', lambda: r.send({'choice': 0}, exercise='unknown/exercise'))
    assert r.catalog.resolutions == 0


@pytest.mark.parametrize('answer', [None, [], {}, 0, True, '0', {'choice': True},
    {'choice': '0'}, {'choice': -1}, {'choice': 1001}, {'choice': 0, 'correct': True},
    {'choice': 0, 'work': 1.5}, {'choice': 0, 'work': float('nan')},
    {'choice': 0, 'work': float('inf')}, {'choice': 0, 'work': 1 << 64}])
def test_incomplete_malformed_and_noncanonical_answers_do_not_change_state(r, answer):
    before = r.state()
    fails('invalid_answer', lambda: r.send(answer), 422)
    assert r.state() == before
    assert r.rule.evaluations == 0


@pytest.mark.parametrize('field,bad,code', [
    ('attempt', '', 'invalid_attempt_id'),
    ('attempt', 'not-a-uuid', 'invalid_attempt_id'),
    ('attempt', True, 'invalid_attempt_id'),
    ('exercise', '', 'invalid_exercise_id'),
    ('exercise', '../outside', 'invalid_exercise_id'),
    ('exercise', 'x' * 257, 'invalid_exercise_id'),
    ('version', 'a' * 63, 'invalid_exercise_version'),
    ('version', 'A' * 64, 'invalid_exercise_version'),
    ('version', True, 'invalid_exercise_version'),
])
def test_invalid_request_identity_never_debits_or_claims_an_attempt(r, field, bad, code):
    before = r.state()
    fails(code, lambda: r.send({'choice': 0}, **{field: bad}), 422)
    assert r.state() == before
    assert r.rule.evaluations == 0


def test_missing_exercise_does_not_claim_attempt_or_charge(r):
    before = r.state()
    attempt = str(uuid4())
    fails('exercise_not_found', lambda: r.send({'choice': 0}, attempt=attempt,
                                              exercise='programming/missing'), 404)
    assert r.state() == before
    # A failed lookup never made this ID a durable attempt.
    assert r.send({'choice': 0}, attempt=attempt)['receipt']['charged_hearts'] == 1


def test_evaluator_exception_rolls_back_result_attempt_and_debit(r):
    before = r.state()
    attempt = str(uuid4())
    r.rule.failure = RuntimeError('deliberately broken evaluator')
    with pytest.raises(RuntimeError, match='deliberately broken evaluator'):
        r.send({'choice': 0}, attempt=attempt)
    assert r.state() == before
    r.rule.failure = None
    assert r.send({'choice': 0}, attempt=attempt)['receipt']['charged_hearts'] == 1
    assert r.h.balance(r.account)['available'] == 7


@pytest.mark.parametrize('route,exercise,capacity', [
    ('programming', EXERCISE, 8), ('math_physics', MATH_EXERCISE, 12),
])
def test_server_catalog_route_selects_the_proper_independent_capacity(r, route, exercise, capacity):
    result = r.send({'choice': 0}, exercise=exercise)
    assert result['hearts']['route'] == route
    assert result['hearts']['maximum'] == capacity
    assert result['hearts']['available'] == capacity - 1
    untouched, expected = ('math_physics', 12) if route == 'programming' else ('programming', 8)
    assert r.h.balance(r.account, route=untouched)['available'] == expected


def test_rollback_clock_does_not_recover_pending_attempt_early(r):
    r.empty()
    start = r.h.time[0]
    attempt = str(uuid4())
    assert r.send({'choice': 0}, attempt=attempt)['status'] == 'pending'
    r.h.time[0] -= H
    assert r.send({'choice': 0}, attempt=attempt)['status'] == 'pending'
    r.h.time[0] = start + H - 1
    assert r.send({'choice': 0}, attempt=attempt)['status'] == 'pending'
    r.h.time[0] += 1
    first = r.send({'choice': 0}, attempt=attempt)
    assert first['receipt']['charged_hearts'] == 1
    r.h.time[0] = start
    replay = r.send({'choice': 0}, attempt=attempt)
    assert replay['receipt'] == first['receipt']
    assert replay['hearts']['available'] == 0
    assert r.rule.evaluations == 1


def test_debt_above_capacity_requires_full_delay_before_pending_evaluation(r):
    other = r.h.register()
    r.h.bind(other, B)
    for _ in range(5):
        r.h.debit(r.account, A)
        r.h.debit(other, B)
    merged = r.h.bind(r.account, B)
    start = r.h.time[0]
    assert merged['hearts']['programming']['next_heart_at_ms'] == start + 3 * H
    attempt = str(uuid4())
    assert r.send({'choice': 0}, attempt=attempt)['status'] == 'pending'
    r.h.time[0] = start + 3 * H - 1
    assert r.send({'choice': 0}, attempt=attempt)['status'] == 'pending'
    assert r.rule.evaluations == 0
    r.h.time[0] += 1
    result = r.send({'choice': 0}, attempt=attempt)
    assert result['receipt']['charged_hearts'] == 1
    assert result['hearts']['available'] == 0
    assert result['hearts']['next_heart_at_ms'] == r.h.time[0] + H
    assert r.h.balance(other, B)['available'] == 0


@pytest.mark.parametrize('point', ['attempt_insert', 'result_insert', 'attempt_complete'])
def test_sql_failure_at_each_receipt_stage_rolls_back_every_mutation(r, point):
    target = {
        'attempt_insert': 'BEFORE INSERT ON evaluation_attempts',
        'result_insert': 'BEFORE INSERT ON evaluation_results',
        'attempt_complete': 'BEFORE UPDATE ON evaluation_attempts',
    }[point]
    attempt = str(uuid4())
    before = r.state()
    with closing(r.h.db.connect()) as con:
        con.execute('CREATE TRIGGER force_evaluation_failure ' + target +
                    " BEGIN SELECT RAISE(ABORT,'forced evaluation rollback'); END")
    with pytest.raises(sqlite3.IntegrityError, match='forced evaluation rollback'):
        r.send({'choice': 0}, attempt=attempt)
    assert r.state() == before
    with closing(r.h.db.connect()) as con:
        con.execute('DROP TRIGGER force_evaluation_failure')
    result = r.send({'choice': 0}, attempt=attempt)
    assert result['receipt']['charged_hearts'] == 1
    assert r.h.balance(r.account)['available'] == 7
    assert r.send({'choice': 0}, attempt=attempt)['receipt'] == result['receipt']


def test_failure_completing_existing_pending_keeps_its_original_identity(r):
    r.empty()
    attempt = str(uuid4())
    r.send({'choice': 0}, attempt=attempt)
    r.h.time[0] += H
    before = r.state()
    with closing(r.h.db.connect()) as con:
        con.execute("""CREATE TRIGGER fail_pending_complete BEFORE UPDATE ON evaluation_attempts
                       BEGIN SELECT RAISE(ABORT,'failed pending complete'); END""")
    with pytest.raises(sqlite3.IntegrityError, match='failed pending complete'):
        r.send({'choice': 0}, attempt=attempt)
    assert r.state() == before
    with closing(r.h.db.connect()) as con:
        con.execute('DROP TRIGGER fail_pending_complete')
    fails('attempt_conflict', lambda: r.send({'choice': 1}, attempt=attempt), 409)
    assert r.send({'choice': 0}, attempt=attempt)['receipt']['charged_hearts'] == 1
    assert r.h.balance(r.account)['available'] == 0


@pytest.mark.parametrize('committed', [False, True])
def test_real_process_exit_before_or_after_commit_never_leaves_partial_charge(r, committed):
    attempt = str(uuid4())
    before = r.state()
    code = '''
import json, os, sys
from pathlib import Path
from contextlib import contextmanager
from servertec import Database, DeviceIdentity
from accounts import AccountStore
from account_ledger import AccountLedger
from consumption_groups import GroupLedger
from evaluations import EvaluationService
from test_evaluations import Catalog
v = json.loads(sys.stdin.read())
db = Database(Path(v['path']), clock=lambda: v['now'])
legacy = AccountLedger(db)
accounts = AccountStore(db, legacy.enroll, firebase_project='test-project')
groups = GroupLedger(db, accounts, legacy, DeviceIdentity(db.path.parent))
service = EvaluationService(groups, Catalog())
original = groups.transaction
@contextmanager
def crash_transaction():
    with original() as con:
        yield con
        if not v['committed']:
            os._exit(37)
    os._exit(38)
groups.transaction = crash_transaction
service.evaluate(v['token'], v['device'], v['attempt'], v['exercise'], v['version'], {'choice': 0})
'''
    child = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).parent,
        input=json.dumps({'path': str(r.h.db.path), 'now': r.h.time[0],
                         'token': r.account['access_token'], 'device': A,
                         'attempt': attempt, 'exercise': EXERCISE, 'version': V1,
                         'committed': committed}),
        text=True, capture_output=True, timeout=15)
    assert child.returncode == (38 if committed else 37), child.stderr
    if not committed:
        assert r.state() == before
    reply = r.send({'choice': 0}, attempt=attempt)
    assert reply['replayed'] is committed
    assert reply['receipt']['charged_hearts'] == 1
    assert r.h.balance(r.account)['available'] == 7
    assert r.send({'choice': 0}, attempt=attempt)['receipt'] == reply['receipt']


def test_installing_evaluator_preserves_existing_accounts_wallets_and_progress(tmp_path):
    h = Harness(tmp_path / 'old-state')
    a = h.register()
    h.bind(a, A)
    h.debit(a)
    h.db.complete(a['account_id'], 'lesson', 'cpp1', 'already_completed')
    h.db.save_settings(a['account_id'], 'ui_language_settings', 0, {'selection': 'fr'})
    tables = ['account_hearts', 'group_hearts', 'consumption_groups', 'group_accounts',
              'group_devices', 'group_account_devices', 'auth_accounts', 'auth_sessions',
              'completions', 'portable_settings']
    before = h.dump(tables)
    EvaluationService(h.groups, Catalog())
    assert h.dump(tables) == before
    EvaluationService(h.groups, Catalog())
    assert h.dump(tables) == before
    assert h.balance(a)['available'] == 7


@pytest.mark.parametrize('table', ['evaluation_meta', 'evaluation_results', 'evaluation_attempts'])
def test_lost_evaluation_schema_refuses_reinitialization_without_restoring_hearts(r, table):
    r.send({'choice': 0})
    before = r.h.dump(['group_hearts'])
    with closing(r.h.db.connect()) as con:
        con.execute('PRAGMA foreign_keys=OFF')
        con.execute('DROP TABLE ' + table)
    with pytest.raises(RuntimeError):
        EvaluationService(r.h.groups, r.catalog)
    assert r.h.dump(['group_hearts']) == before
    with closing(r.h.db.connect()) as con:
        assert con.execute('SELECT 1 FROM sqlite_master WHERE type=\'table\' AND name=?',
                           (table,)).fetchone() is None


def test_removing_all_evaluation_tables_still_cannot_erase_the_durable_guard(r):
    r.send({'choice': 0})
    before = r.h.dump(['group_hearts'])
    with closing(r.h.db.connect()) as con:
        con.execute('PRAGMA foreign_keys=OFF')
        for table in ('evaluation_attempts', 'evaluation_results', 'evaluation_meta'):
            con.execute('DROP TABLE ' + table)
    with pytest.raises(RuntimeError):
        EvaluationService(r.h.groups, r.catalog)
    assert r.h.dump(['group_hearts']) == before


def test_runtime_missing_wallet_blocks_even_a_previously_confirmed_receipt(r):
    attempt = str(uuid4())
    result = r.send({'choice': 0}, attempt=attempt)
    with closing(r.h.db.connect()) as con:
        con.execute("DELETE FROM group_hearts WHERE group_id=? AND route='programming'",
                    (result['hearts']['group_id'],))
    before = r.state()
    fails('wallet_state_missing', lambda: r.send({'choice': 0}, attempt=attempt), 503)
    assert r.state() == before


def test_receipt_tables_do_not_persist_raw_answers_or_authentication_material(r):
    phrase = 'private-unsubmitted-work-a7c0e983'
    r.send({'choice': 0, 'work': phrase})
    with closing(r.h.db.connect()) as con:
        rows = {name: con.execute('SELECT * FROM ' + name).fetchall()
                for name in ('evaluation_results', 'evaluation_attempts')}
    text = json.dumps(rows)
    for private in (phrase, r.account['access_token'], r.account['recovery_code'], PASS, A):
        assert private not in text
