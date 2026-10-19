"""Disposable SQLite and HTTP tests for shared free-use histories.

Debit tests use the internal primitive, not a pretend public puzzle evaluator.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import consumption_groups
from consumption_groups import GroupLedger, CONFIRMATION_MS
from account_ledger import AccountLedger, HOUR_MS as H, LedgerError
from accounts import AccountStore, AccountError, _opaque_digest
from servertec import Database, DeviceIdentity, Settings, create_app

PASS = 'A private test password long enough'
A, B, C, D = ['abcdef000000000' + str(i) for i in range(4)]


class TestHasher:
    """Only for state-machine tests. One HTTP test below uses real scrypt."""
    __test__ = False
    dummy_hash = '0' * 64
    def hash(self, password):
        return hashlib.sha256(password.encode()).hexdigest()
    def verify(self, password, encoded):
        return hmac.compare_digest(self.hash(password), encoded)


class Harness:
    def __init__(self, state, *, migrated=False):
        self.time = [1_800_000_000_000]
        self.db = Database(state / 'servertec.db', clock=lambda: self.time[0])
        self.legacy = AccountLedger(self.db)
        self.accounts = AccountStore(self.db, self.legacy.enroll, hasher=TestHasher(),
                                     firebase_project='test-project')
        self.identities = DeviceIdentity(state)
        self.number = 0
        if not migrated:
            self.enable_groups()

    def enable_groups(self):
        self.groups = GroupLedger(self.db, self.accounts, self.legacy, self.identities)
        self.accounts.on_enroll = self.groups.enroll

    def register(self, *, google=False):
        self.number += 1
        invite = self.accounts.issue_invitation()['invitation']
        peer = '192.0.2.' + str((self.number % 254) + 1)
        if google:
            return self.accounts.google_login('google-' + str(self.number), invite, peer,
                                              expires_at_ms=self.time[0] + 3600_000)
        return self.accounts.register('User' + str(self.number), PASS, invite, peer)

    def begin(self, account, device=A):
        return self.groups.prepare(account['access_token'], device)

    def bind(self, account, device=A):
        reply = self.begin(account, device)
        if reply['status'] == 'confirmation_required':
            return self.groups.confirm(account['access_token'], device, reply['confirmation_token'])
        return reply

    def debit(self, account, device=A, route='programming'):
        with self.groups.transaction() as con:
            return self.groups.debit_in_transaction(con, account['access_token'], device, route)

    def balance(self, account, device=A, route='programming'):
        return self.groups.snapshot(account['access_token'], device, route)

    def dump(self, tables=None):
        tables = tables or ('consumption_groups', 'group_accounts', 'group_devices',
                            'group_account_devices', 'group_hearts', 'auth_accounts',
                            'auth_google', 'completions', 'portable_settings')
        with closing(self.db.connect()) as con:
            return {name: con.execute('SELECT * FROM ' + name + ' ORDER BY rowid').fetchall() for name in tables}

    def client(self, account=None, device=A):
        app = create_app(Settings(self.db.path.parent, testing=False, project_id='test-project'),
                         self.db, accounts=self.accounts)
        c = TestClient(app, base_url='https://127.0.0.1', client=('127.0.0.1', 55000))
        if account:
            c.headers['Authorization'] = 'Bearer ' + account['access_token']
        if device is not None:
            c.headers['X-Android-Id'] = device
        return c


@pytest.fixture
def h(tmp_path):
    return Harness(tmp_path / 'state')


def expect(code, call):
    with pytest.raises((LedgerError, AccountError)) as err:
        call()
    assert err.value.code == code
    return err.value


def test_five_accounts_share_eight_hearts_and_one_recovery(h):
    accounts = [h.register() for _ in range(5)]
    groups = [h.bind(a)['group_id'] for a in accounts]
    for i in range(8):
        assert h.debit(accounts[i % 5])['available'] == 7 - i
    roots = {h.balance(a)['group_id'] for a in accounts}
    assert len(roots) == 1
    assert all(h.balance(a)['available'] == 0 for a in accounts)
    assert all(h.balance(a, route='math_physics')['available'] == 12 for a in accounts)
    h.time[0] += H
    assert all(h.balance(a)['available'] == 1 for a in accounts)
    assert h.debit(accounts[4])['available'] == 0
    assert all(h.balance(a)['available'] == 0 for a in accounts)
    with closing(h.db.connect()) as con:
        assert con.execute('SELECT COUNT(*) FROM consumption_groups WHERE parent_id IS NULL').fetchone()[0] == 1


def test_new_account_cannot_refill_an_already_depleted_device(h):
    one = h.register(); h.bind(one)
    for _ in range(8): h.debit(one)
    two = h.register()
    expect('device_confirmation_required', lambda: h.balance(two))
    initial = h.begin(two)
    assert initial['status'] == 'linked'
    assert initial['hearts']['programming']['available'] == 0
    assert h.debit(two)['status'] == 'empty'


def test_cancellation_never_changes_wallets_groups_accounts_or_old_session(h):
    one, two = h.register(), h.register()
    h.bind(one, A); h.bind(two, B)
    h.debit(one, A); h.debit(two, B)
    before = h.dump()
    pending = h.begin(one, B)
    assert pending['status'] == 'confirmation_required'
    assert h.dump() == before
    h.time[0] += 60_000
    assert h.groups.cancel(one['access_token'], B, pending['confirmation_token']) == {'status': 'cancelled'}
    assert h.dump() == before  # cancellation does not even checkpoint recovery
    expect('device_confirmation_cancelled', lambda: h.groups.confirm(one['access_token'], B, pending['confirmation_token']))
    expect('device_confirmation_required', lambda: h.balance(one, B))
    assert h.accounts.authenticate(one['access_token']) == one['account_id']
    assert h.balance(one, A)['available'] == 7


def test_merge_two_five_hour_debts_without_forgiving_excess(h):
    one, two = h.register(), h.register()
    h.bind(one, A); h.bind(two, B)
    for _ in range(5): h.debit(one, A); h.debit(two, B)
    merged = h.bind(one, B)
    balance = merged['hearts']['programming']
    assert balance['available'] == 0
    assert balance['next_heart_at_ms'] == h.time[0] + 3 * H
    assert h.balance(two, B)['group_id'] == merged['group_id']
    h.time[0] += 3 * H - 1
    assert h.balance(one, A)['available'] == 0
    h.time[0] += 1
    assert h.balance(two, B)['available'] == 1


def test_transitive_merges_retarget_all_aliases_and_old_sessions(h):
    people = [h.register() for _ in range(4)]
    devices = (A, B, C, D)
    original = [h.bind(a, d)['group_id'] for a, d in zip(people, devices)]
    for a, d in zip(people, devices): h.debit(a, d)
    h.bind(people[0], B)
    h.bind(people[2], D)
    h.bind(people[0], C)
    roots = [h.balance(a, d)['group_id'] for a, d in zip(people, devices)]
    assert len(set(roots)) == 1 and roots[0] == min(original)
    assert all(h.balance(a, d)['available'] == 4 for a, d in zip(people, devices))
    with h.groups.transaction() as con:
        assert {h.groups._root(con, old)['group_id'] for old in original} == {roots[0]}
    for a, d in zip(people, devices):
        h.begin(a, d)
    assert h.balance(people[0], A)['available'] == 4


def test_oldest_root_wins_even_when_device_group_is_older(h):
    first = h.register(); old = h.bind(first, A)['group_id']
    h.time[0] += 50
    second = h.register(); h.bind(second, B)
    assert h.bind(second, A)['group_id'] == old


def test_same_root_association_never_adds_debt_twice(h):
    one, two = h.register(), h.register()
    h.bind(one, A); h.bind(one, B); h.bind(two, A)
    h.debit(one, B)
    p = h.begin(two, B)
    assert p['status'] == 'confirmation_required'
    h.groups.confirm(two['access_token'], B, p['confirmation_token'])
    for _ in range(3):
        r = h.groups.confirm(two['access_token'], B, p['confirmation_token'])
        assert r['replayed'] and r['hearts']['programming']['available'] == 7
    assert h.balance(one, A)['available'] == 7


@pytest.mark.parametrize('change', ['account_group', 'device_group', 'new_device_claim'])
def test_pending_scope_changed_requires_a_new_confirmation(h, change):
    one, two, three = [h.register() for _ in range(3)]
    h.bind(one, A); h.bind(two, B); h.bind(three, C)
    target = D if change == 'new_device_claim' else B
    p = h.begin(one, target)
    if change == 'account_group': h.bind(one, C)
    elif change == 'device_group': h.bind(two, C)
    else: h.bind(three, D)
    before = h.dump()
    expect('device_confirmation_stale', lambda: h.groups.confirm(one['access_token'], target, p['confirmation_token']))
    assert h.dump() == before
    newer = h.begin(one, target)
    assert newer['confirmation_token'] != p['confirmation_token']
    assert h.groups.confirm(one['access_token'], target, newer['confirmation_token'])['status'] == 'linked'


def test_spending_during_warning_does_not_stale_membership_or_ignore_debt(h):
    one, two = h.register(), h.register(); h.bind(one, A); h.bind(two, B)
    p = h.begin(one, B)
    h.debit(two, B)
    result = h.groups.confirm(one['access_token'], B, p['confirmation_token'])
    assert result['hearts']['programming']['available'] == 7


@pytest.mark.parametrize('replacement', ['new_session', 'other_account', 'other_device', 'arbitrary_token'])
def test_confirmation_is_bound_to_account_session_device_and_nonce(h, replacement):
    one, two = h.register(), h.register(); h.bind(one, A); h.bind(two, B)
    p = h.begin(one, C); token, device, challenge = one['access_token'], C, p['confirmation_token']
    if replacement == 'new_session': token = h.accounts.login(one['username'], PASS, '127.0.0.1')['access_token']
    elif replacement == 'other_account': token = two['access_token']
    elif replacement == 'other_device': device = D
    else: challenge = 'gc1_' + 'A' * 43
    before = h.dump()
    expect('invalid_device_confirmation', lambda: h.groups.confirm(token, device, challenge))
    assert h.dump() == before


@pytest.mark.parametrize('delta', [CONFIRMATION_MS, CONFIRMATION_MS + 1, -1])
def test_expired_or_rollback_confirmation_cannot_authorize(h, delta):
    a = h.register(); h.bind(a, A); p = h.begin(a, B)
    before = h.dump()
    h.time[0] += delta
    expect('device_confirmation_expired', lambda: h.groups.confirm(a['access_token'], B, p['confirmation_token']))
    assert h.dump() == before


@pytest.mark.parametrize('mutation', ['logout', 'disable', 'recover'])
def test_revocation_between_prepare_and_confirm_blocks_union(h, mutation):
    a = h.register(); h.bind(a, A); p = h.begin(a, B)
    before = h.dump(['consumption_groups','group_devices','group_account_devices','group_hearts'])
    if mutation == 'logout': h.accounts.logout(a['access_token'])
    elif mutation == 'disable': h.accounts.disable_account(a['account_id'])
    else: h.accounts.recover(a['username'], a['recovery_code'], 'a newly chosen secret phrase', '127.0.0.1')
    expect('invalid_credentials', lambda: h.groups.confirm(a['access_token'], B, p['confirmation_token']))
    assert h.dump(list(before)) == before


def test_key_missing_or_rotated_never_issues_new_device_identity(h):
    a = h.register(); h.bind(a, A); h.debit(a)
    secret = h.identities.path.read_bytes(); before = h.dump()
    h.identities.path.unlink()
    expect('device_key_unavailable', lambda: h.begin(a, A))
    assert not h.identities.path.exists()
    h.identities.path.write_bytes(b'z' * 32)
    expect('device_key_changed', lambda: h.begin(a, A))
    assert h.dump() == before
    h.identities.path.write_bytes(secret)
    assert h.balance(a)['available'] == 7


def test_restart_login_recovery_and_device_case_preserve_balance(h):
    a = h.register(); h.bind(a, A); h.debit(a)
    h.enable_groups()
    assert h.balance(a, A.upper())['available'] == 7
    h.accounts.recover(a['username'], a['recovery_code'], 'a new secret recovery password', '127.0.0.1')
    a2 = h.accounts.login(a['username'].lower(), 'a new secret recovery password', '127.0.0.1')
    assert a2['account_id'] == a['account_id']
    assert h.begin(a2, A)['status'] == 'linked'
    assert h.balance(a2)['available'] == 7


@pytest.mark.parametrize('bad', [None, '', 'abcd', 'g' * 16, 'a' * 17, True, 'a' * 16 + '\n'])
def test_bad_device_values_never_bind_or_grant(h, bad):
    a = h.register(); before = h.dump()
    expect('invalid_device', lambda: h.begin(a, bad))
    assert h.dump() == before


def test_merged_accounts_do_not_share_private_data_or_recovery_codes(h):
    a, b = h.register(), h.register()
    h.db.complete(a['account_id'], 'lesson', 'cpp1', 'a_only')
    h.db.complete(b['account_id'], 'lesson', 'math1', 'b_only')
    h.db.save_settings(a['account_id'], 'ui_language_settings', 0, {'selection': 'fr'})
    before = h.dump(['auth_accounts','auth_google','completions','portable_settings'])
    h.bind(a, A); h.bind(b, A)
    assert h.dump(list(before)) == before
    expect('invalid_credentials', lambda: h.accounts.recover(b['username'], a['recovery_code'], PASS, '127.0.0.1'))
    with h.client(b, A) as c:
        result = c.get('/v2/progress', headers={'X-User-Id':a['account_id']})
        assert [p['item'] for p in result.json()['completed']] == ['b_only']
        assert a['account_id'] not in result.text


def test_unbound_login_does_not_block_identity_progress_or_premium_route(h):
    a = h.register(); h.bind(a, A)
    with h.client(a, B) as c:
        assert c.get('/v2/auth/me').status_code == 200
        assert c.get('/v2/progress').status_code == 200
        assert c.get('/v2/hearts/programming').json() == {'error':'device_confirmation_required'}
        # This server stage has no billing API and no Premium propagation.
        assert c.post('/v2/premium', json={'premium':True}).status_code == 404


def test_failed_merge_rolls_back_every_part_and_same_token_remains_usable(h):
    a, b = h.register(), h.register(); h.bind(a, A); h.bind(b, B)
    h.debit(a, A); h.debit(b, B)
    pending = h.begin(a, B)
    before = h.dump()
    with closing(h.db.connect()) as con:
        con.execute("""CREATE TRIGGER fail_link BEFORE INSERT ON group_account_devices
                       BEGIN SELECT RAISE(ABORT,'forced rollback'); END""")
    with pytest.raises(sqlite3.IntegrityError, match='forced rollback'):
        h.groups.confirm(a['access_token'], B, pending['confirmation_token'])
    assert h.dump() == before
    with closing(h.db.connect()) as con: con.execute('DROP TRIGGER fail_link')
    result = h.groups.confirm(a['access_token'], B, pending['confirmation_token'])
    assert result['hearts']['programming']['available'] == 6


def test_abrupt_real_child_exit_during_merge_rolls_back(h):
    a, b = h.register(), h.register(); h.bind(a, A); h.bind(b, B)
    h.debit(a, A); h.debit(b, B); p = h.begin(a, B); before = h.dump()
    code = '''
import sys,json,os
from pathlib import Path
from servertec import Database,DeviceIdentity
from accounts import AccountStore
from account_ledger import AccountLedger
from consumption_groups import GroupLedger
values=json.loads(sys.stdin.read());db=Database(Path(values['path']),clock=lambda:values['now'])
old=AccountLedger(db);accounts=AccountStore(db,old.enroll,firebase_project='test-project')
class Crash(GroupLedger):
    def _merge(self,*args):
        super()._merge(*args)
        os._exit(37)
g=Crash(db,accounts,old,DeviceIdentity(db.path.parent))
g.confirm(values['session'],values['device'],values['challenge'])
'''
    # Secrets travel through private process stdin, not command-line arguments.
    child = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).parent,
        input=json.dumps(dict(path=str(h.db.path), now=h.time[0], session=a['access_token'],
                              device=B, challenge=p['confirmation_token'])),
        text=True, capture_output=True, timeout=15)
    assert child.returncode == 37, child.stderr
    assert h.dump() == before
    assert h.groups.confirm(a['access_token'], B, p['confirmation_token'])['hearts']['programming']['available'] == 6


def test_many_parallel_confirmations_merge_debt_once(h):
    a, b = h.register(), h.register(); h.bind(a, A); h.bind(b, B)
    h.debit(a, A); h.debit(b, B); p = h.begin(a, B)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _:h.groups.confirm(a['access_token'],B,p['confirmation_token']),range(24)))
    assert sum(not x['replayed'] for x in results) == 1
    assert h.balance(a, A)['available'] == 6


def test_parallel_new_accounts_on_one_device_have_one_root(h):
    people = [h.register() for _ in range(5)]
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(lambda a:h.begin(a,A), people))
    assert len({h.balance(a, A)['group_id'] for a in people}) == 1
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda i:h.debit(people[i%5], A), range(24)))
    assert sum(r['status']=='charged' for r in responses) == 8


def test_idempotent_caller_receipt_stays_account_scoped_across_merge(h):
    a, b = h.register(), h.register(); h.bind(a, A); h.bind(b, B)
    with closing(h.db.connect()) as con:
        con.execute('CREATE TABLE test_receipts(uid TEXT,op TEXT,reply TEXT,PRIMARY KEY(uid,op))')
    op = str(uuid4())
    def internal_attempt():
        with h.groups.transaction() as con:
            uid, _ = h.groups.authorize_in_transaction(con,a['access_token'],A)
            previous = con.execute('SELECT reply FROM test_receipts WHERE uid=? AND op=?',(uid,op)).fetchone()
            if previous: return json.loads(previous[0])
            r = h.groups.debit_in_transaction(con,a['access_token'],A,'programming')
            con.execute('INSERT INTO test_receipts VALUES(?,?,?)',(uid,op,json.dumps(r)))
            return r
    p = h.begin(a,B)
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = [pool.submit(internal_attempt) for _ in range(20)]
        jobs.append(pool.submit(h.groups.confirm,a['access_token'],B,p['confirmation_token']))
        for job in jobs: job.result()
    assert h.balance(a,A)['available'] == h.balance(b,B)['available'] == 7
    assert internal_attempt()['status'] == 'charged'
    assert h.balance(a,A)['available'] == 7


def test_old_account_migration_preserves_debt_and_requires_first_link_consent(tmp_path):
    h = Harness(tmp_path/'state', migrated=True)
    a = h.register()
    with closing(h.db.connect()) as con:
        con.execute('BEGIN IMMEDIATE');h.legacy.debit_in_transaction(con,a['account_id'],'programming');con.commit()
    h.db.complete(a['account_id'],'lesson','cpp1','l1')
    before = h.dump(['account_hearts','auth_accounts','completions'])
    h.enable_groups()
    assert h.dump(list(before)) == before
    expect('device_confirmation_required', lambda:h.balance(a,A))
    assert h.begin(a,A)['status']=='confirmation_required'
    assert h.bind(a,A)['hearts']['programming']['available']==7
    h.enable_groups()
    assert h.balance(a,A)['available']==7


def test_google_legacy_import_and_google_new_accounts_use_same_gate(tmp_path):
    h = Harness(tmp_path/'state', migrated=True)
    # Add legacy eligibility as if the first auth migration had captured this UID.
    h.db.hearts('legacy-google','programming',str(uuid4()))
    with closing(h.db.connect()) as con:
        con.execute("INSERT INTO auth_legacy_eligible VALUES('legacy-google')")
    h.enable_groups()
    old = h.accounts.google_login('legacy-google',None,'127.0.0.1',expires_at_ms=h.time[0]+3600_000)
    assert h.begin(old,A)['status']=='confirmation_required'
    assert h.bind(old,A)['hearts']['programming']['available']==7
    new = h.register(google=True)
    assert h.begin(new,A)['status']=='linked'
    assert h.balance(new,A)['available']==7
    assert h.begin(new,B)['status']=='confirmation_required'


def test_migration_missing_wallet_fails_without_partial_schema_or_grants(tmp_path):
    h = Harness(tmp_path/'state', migrated=True);a=h.register()
    with closing(h.db.connect()) as con:
        con.execute("DELETE FROM account_hearts WHERE uid=? AND route='programming'",(a['account_id'],))
    before=h.dump(['account_hearts','auth_accounts'])
    with pytest.raises(LedgerError,match='wallet_state_missing'):h.enable_groups()
    assert h.dump(list(before))==before
    with closing(h.db.connect()) as con:
        assert con.execute("SELECT 1 FROM sqlite_master WHERE name='group_meta'").fetchone() is None
        assert con.execute("SELECT 1 FROM auth_meta WHERE key='consumption_groups'").fetchone() is None


def test_missing_runtime_wallet_or_account_mapping_never_reseeds(h):
    a=h.register();h.bind(a,A);gid=h.balance(a)['group_id']
    with closing(h.db.connect()) as con:
        con.execute("DELETE FROM group_hearts WHERE group_id=? AND route='programming'",(gid,))
    expect('wallet_state_missing',lambda:h.balance(a,A))
    expect('wallet_state_missing',lambda:h.begin(a,A))
    with closing(h.db.connect()) as con:
        assert con.execute('SELECT COUNT(*) FROM group_hearts WHERE group_id=?',(gid,)).fetchone()[0]==1
        con.execute('DELETE FROM group_accounts WHERE account_id=?',(a['account_id'],))
    expect('group_state_missing',lambda:h.begin(a,A))
    with pytest.raises(RuntimeError,match='missing shared history'):h.enable_groups()


@pytest.mark.parametrize('target',['group_meta','group_devices','group_archive_update'])
def test_missing_schema_objects_refuse_reinitialization(h,target):
    a=h.register();h.bind(a,A)
    with closing(h.db.connect()) as con:
        con.execute('PRAGMA foreign_keys=OFF')
        kind='TRIGGER' if target.startswith('group_archive') else 'TABLE'
        con.execute('DROP '+kind+' '+target)
    with pytest.raises(RuntimeError):h.enable_groups()


def test_archived_account_wallet_cannot_be_changed_by_legacy_primitive(h):
    a=h.register();h.bind(a,A)
    with closing(h.db.connect()) as con:
        con.execute('BEGIN IMMEDIATE')
        with pytest.raises(sqlite3.IntegrityError,match='account_wallet_is_archived'):
            h.legacy.debit_in_transaction(con,a['account_id'],'programming')
        con.rollback()
    assert h.balance(a,A)['available']==8


def test_cleanup_and_reprepare_keep_challenge_storage_bounded(h):
    a=h.register();h.bind(a,A)
    previous=None
    for _ in range(20):
        p=h.begin(a,B)
        if previous:expect('invalid_device_confirmation',lambda:h.groups.confirm(a['access_token'],B,previous))
        previous=p['confirmation_token']
    with closing(h.db.connect()) as con:assert con.execute('SELECT COUNT(*) FROM group_confirmations').fetchone()[0]==1
    for n in range(7):h.begin(a,f'{n+100:016x}')
    expect('device_confirmation_limit',lambda:h.begin(a,D))
    h.time[0]+=CONFIRMATION_MS
    assert h.begin(a,D)['status']=='confirmation_required'
    with closing(h.db.connect()) as con:assert con.execute('SELECT COUNT(*) FROM group_confirmations').fetchone()[0]==1


def test_sql_dump_does_not_contain_raw_device_ids_or_confirmation_tokens(h):
    a=h.register();h.bind(a,A);p=h.begin(a,B)
    with closing(h.db.connect()) as con:text='\n'.join(con.iterdump())
    for secret in (A,B,p['confirmation_token'],a['access_token'],PASS):assert secret not in text


def test_clock_rollback_then_hour_boundary_does_not_duplicate_recovery(h):
    a=h.register();h.bind(a,A);h.debit(a,A);start=h.time[0]
    h.time[0]-=100*H;assert h.balance(a,A)['available']==7
    h.time[0]=start+H-1;assert h.balance(a,A)['available']==7
    h.time[0]+=1;assert h.balance(a,A)['available']==8
    h.time[0]+=100*H;h.debit(a,A);assert h.balance(a,A)['next_heart_at_ms']==h.time[0]+H


def test_merge_normalizes_each_anchor_without_crediting_future_time(h):
    a,b=h.register(),h.register();ga=h.bind(a,A)['group_id'];gb=h.bind(b,B)['group_id'];now=h.time[0]
    with closing(h.db.connect()) as con:
        con.execute("UPDATE group_hearts SET debt_ms=?,anchor_ms=? WHERE group_id=? AND route='programming'",(5*H,now+10*H,ga))
        con.execute("UPDATE group_hearts SET debt_ms=?,anchor_ms=? WHERE group_id=? AND route='programming'",(4*H,now-2*H,gb))
    r=h.bind(a,B)['hearts']['programming']
    assert r['available']==1 and r['next_heart_at_ms']==now+11*H


def test_connections_close_after_success_exception_and_failed_startup(h,monkeypatch):
    kept=[];original=sqlite3.connect
    class Tracked(sqlite3.Connection):
        closed=False
        def close(self):super().close();self.closed=True
    def connect(*a,**kw):
        kw['factory']=Tracked;c=original(*a,**kw);kept.append(c);return c
    monkeypatch.setattr(sqlite3,'connect',connect)
    a=h.register();h.bind(a,A);h.debit(a,A)
    p=h.begin(a,B);h.groups.cancel(a['access_token'],B,p['confirmation_token'])
    expect('device_confirmation_cancelled',lambda:h.groups.confirm(a['access_token'],B,p['confirmation_token']))
    h.enable_groups()
    assert kept and all(c.closed for c in kept)


def test_http_confirmation_gate_and_strict_body(h):
    a=h.register()
    with h.client(a,A) as c:
        assert c.get('/v2/hearts/programming').status_code==409
        assert c.post('/v2/devices/prepare').json()['status']=='linked'
        c.headers['X-Android-Id']=B
        p=c.post('/v2/devices/prepare').json()
        assert c.get('/v2/hearts/programming').status_code==409
        for body in ({'confirmed':True},{'confirmation_token':p['confirmation_token'],'account_id':'x'},
                     {'confirmation_token':p['confirmation_token'],'premium':True}):
            assert c.post('/v2/devices/confirm',json=body).status_code==422
        r=c.post('/v2/devices/confirm',json={'confirmation_token':p['confirmation_token']})
        assert r.status_code==200 and r.headers['cache-control']=='no-store'
        assert c.get('/v2/hearts/programming').json()['available']==8
        c.headers.pop('X-Android-Id')
        assert c.get('/v2/hearts/programming').status_code==422
        assert c.get('/v2/auth/me').status_code==200
        c.headers.pop('Authorization')
        assert c.post('/v2/devices/prepare').status_code==401
        assert c.get('/v1/hearts/programming').status_code==410
        assert c.post('/v2/hearts/debits',json={'route':'programming','operation_id':str(uuid4())}).status_code in (404,405)


def test_backup_preserves_groups_and_needs_same_existing_private_key(h,tmp_path):
    a,b=h.register(),h.register();h.bind(a,A);h.bind(b,A);h.debit(a)
    target=tmp_path/'copy'/'servertec.db';target.parent.mkdir()
    h.db.backup(target)
    (target.parent/'device-hmac.key').write_bytes(h.identities.path.read_bytes())
    db=Database(target,clock=lambda:h.time[0]);legacy=AccountLedger(db)
    accounts=AccountStore(db,legacy.enroll,firebase_project='test-project')
    g=GroupLedger(db,accounts,legacy,DeviceIdentity(target.parent))
    assert g.snapshot(a['access_token'],A,'programming')['available']==7
    assert g.snapshot(b['access_token'],A,'programming')['available']==7


def test_new_enrollment_failure_keeps_invitation_and_account_atomic(h,monkeypatch):
    invite=h.accounts.issue_invitation()['invitation'];before=h.dump()
    old=h.groups._import_account
    def broken(*args,**kwargs):
        old(*args,**kwargs)
        raise RuntimeError('group import failed')
    monkeypatch.setattr(h.groups,'_import_account',broken)
    with pytest.raises(RuntimeError,match='group import failed'):
        h.accounts.register('failure_user',PASS,invite,'127.0.0.1')
    assert h.dump()==before
    monkeypatch.setattr(h.groups,'_import_account',old)
    assert h.accounts.register('failure_user',PASS,invite,'127.0.0.1')['account_id']


def test_real_scrypt_registration_login_and_shared_device_http(tmp_path):
    state=tmp_path/'state';db=Database(state/'servertec.db');old=AccountLedger(db)
    accounts=AccountStore(db,old.enroll,firebase_project='test-project')
    app=create_app(Settings(state,testing=False,project_id='test-project'),db,accounts=accounts)
    with TestClient(app,base_url='https://127.0.0.1',client=('127.0.0.1',55000)) as c:
        identities=[]
        for username in ('real_a','real_b'):
            r=c.post('/v2/auth/register',json={'username':username,'password':PASS,
                                              'invitation':accounts.issue_invitation()['invitation']})
            assert r.status_code==201
            identities.append(r.json())
            c.headers.update({'Authorization':'Bearer '+r.json()['access_token'],'X-Android-Id':A})
            assert c.post('/v2/devices/prepare').json()['status']=='linked'
        ga=c.get('/v2/hearts/programming').json()['group_id']
        r=c.post('/v2/auth/login',json={'username':'REAL_A','password':PASS})
        assert r.status_code==200 and r.json()['account_id']==identities[0]['account_id']
        c.headers['Authorization']='Bearer '+r.json()['access_token']
        assert c.get('/v2/hearts/programming').json()['group_id']==ga


def test_prepare_rejects_client_identity_and_confirmation_fields(h):
    a = h.register()
    with h.client(a, A) as c:
        for body in ({'confirmed': True}, {'group_id': 'forged'}, {'balance': 99}):
            assert c.post('/v2/devices/prepare', json=body).status_code == 422
        assert c.get('/v2/hearts/programming').status_code == 409
        assert c.post('/v2/devices/prepare', json={}).json()['status'] == 'linked'


def test_confirmation_checks_expiry_after_waiting_for_writer(h, monkeypatch):
    import threading
    from contextlib import contextmanager
    a = h.register(); h.bind(a, A); pending = h.begin(a, B)
    entering = threading.Event(); original = h.groups.transaction
    @contextmanager
    def observed():
        entering.set()
        with original() as con:
            yield con
    monkeypatch.setattr(h.groups, 'transaction', observed)
    holder = h.db.connect()
    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            holder.execute('BEGIN IMMEDIATE')
            job = pool.submit(h.groups.confirm, a['access_token'], B, pending['confirmation_token'])
            assert entering.wait(5)
            h.time[0] += CONFIRMATION_MS
            holder.commit()
        finally:
            holder.close()
        expect('device_confirmation_expired', job.result)
    expect('device_confirmation_required', lambda: h.balance(a, B))


def test_foreign_database_injection_is_rejected(h, tmp_path):
    other = Database(tmp_path / 'other' / 'servertec.db')
    with pytest.raises(ValueError, match='same database'):
        GroupLedger(other, h.accounts, AccountLedger(other), h.identities)


@pytest.mark.parametrize('route', ['programming', 'math_physics'])
def test_random_sequence_matches_independent_group_accounting(h, route):
    import random
    random = random.Random(907)
    people = [h.register() for _ in range(5)]
    devices = [f'{200 + i:016x}' for i in range(5)]
    for person, device in zip(people, devices): h.bind(person, device)
    sets = [{i} for i in range(5)]
    debts = [0 for _ in people]
    cap = 8 if route == 'programming' else 12
    for _ in range(200):
        delta = random.randrange(6 * 60_000, H + 1)
        h.time[0] += delta
        debts = [max(0, value - delta) for value in debts]
        i, j = random.sample(range(5), 2)
        ri = next(k for k, group in enumerate(sets) if i in group)
        if random.randrange(2):
            rj = next(k for k, group in enumerate(sets) if j in group)
            h.bind(people[i], devices[j])
            if ri != rj:
                debts[ri] += debts[rj]; debts[rj] = 0
                sets[ri] |= sets[rj]; sets[rj] = set()
        else:
            result = h.debit(people[i], devices[i], route)
            enough = debts[ri] <= (cap - 1) * H
            assert result['status'] == ('charged' if enough else 'empty')
            if enough: debts[ri] += H
        for k in range(5):
            root = next(n for n, group in enumerate(sets) if k in group)
            expected = max(0, cap * H - debts[root]) // H
            assert h.balance(people[k], devices[k], route)['available'] == expected
