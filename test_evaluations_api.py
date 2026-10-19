"""HTTP boundaries plus a real TLS subprocess with the installed curriculum."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from account_ledger import AccountLedger, HOUR_MS
from accounts import AccountStore
from autoprueba import private_tls_context, stop_owned_process
from exercise_catalog import ExerciseCatalog
from manage import make_pki, write_private
from servertec import Database, Settings, create_app
from test_consumption_groups import Harness, PASS, A, B
from test_evaluations import Catalog, EXERCISE, V1


@pytest.fixture
def api(tmp_path):
    h = Harness(tmp_path / 'state')
    account = h.register()
    h.bind(account)
    catalog = Catalog()
    app = create_app(Settings(h.db.path.parent, testing=False, project_id='test-project'),
                     h.db, accounts=h.accounts, catalog=catalog)
    with TestClient(app, base_url='https://127.0.0.1', client=('127.0.0.1', 55100)) as client:
        client.headers.update({'Authorization': 'Bearer ' + account['access_token'], 'X-Android-Id': A})
        yield h, account, catalog, client


def body(answer=None):
    return {'attempt_id': str(uuid4()), 'exercise_id': EXERCISE,
            'exercise_version': V1, 'answer': {'choice': 0} if answer is None else answer}


def test_http_result_receipt_and_current_balance_share_one_response(api):
    h, account, catalog, client = api
    request = body()
    result = client.post('/v2/evaluations', json=request)
    assert result.status_code == 200
    payload = result.json()
    assert payload['receipt']['correct'] is False
    assert payload['receipt']['charged_hearts'] == 1
    assert payload['hearts']['available'] == 7
    assert payload['hearts']['next_heart_at_ms'] == h.time[0] + HOUR_MS
    assert payload['hearts']['account_id'] == account['account_id']
    assert result.headers['cache-control'] == 'no-store'
    assert result.headers['x-content-type-options'] == 'nosniff'
    repeated = client.post('/v2/evaluations', json=request).json()
    assert repeated['replayed'] is True
    assert repeated['receipt'] == payload['receipt']
    assert repeated['hearts']['available'] == 7
    assert catalog.rules[EXERCISE, V1].evaluations == 1
    good = client.post('/v2/evaluations', json=body({'choice': 2})).json()
    assert good['receipt']['correct'] is True
    assert good['receipt']['charged_hearts'] == 0
    assert good['hearts']['available'] == 7


@pytest.mark.parametrize('extra', [
    {'correct': True}, {'correcto': True}, {'saldo': 8}, {'premium': True},
    {'route': 'math_physics'}, {'account_id': 'another-account'}, {'group_id': 'another-group'},
    {'validator': {'answer': 0}}, {'result': 'correct'},
])
def test_client_cannot_supply_authority(api, extra):
    h, account, _, client = api
    before = h.dump()
    result = client.post('/v2/evaluations', json={**body(), **extra})
    assert result.status_code == 422
    assert result.json() == {'error': 'invalid_request'}
    assert h.dump() == before


@pytest.mark.parametrize('mutation', [
    'duplicate_answer', 'duplicate_nested_key', 'nan', 'infinity', 'null',
    'too_deep', 'boolean_choice', 'string_choice', 'float_choice', 'bad_uuid',
    'invalid_unicode', 'invalid_utf8',
])
def test_bad_json_is_rejected_without_charge_or_echo(api, mutation):
    h, account, _, client = api
    request = body()
    text = json.dumps(request)
    if mutation == 'duplicate_answer':
        text = text[:-1] + ', "answer": {"choice": 2}}'
    elif mutation == 'duplicate_nested_key':
        text = text.replace('"choice": 0', '"choice": 0, "choice": 2')
    elif mutation in ('nan', 'infinity'):
        text = text.replace('"choice": 0', '"choice": ' + ('NaN' if mutation == 'nan' else 'Infinity'))
    elif mutation == 'null':
        text = 'null'
    elif mutation == 'too_deep':
        text = text.replace('"choice": 0', '"choice": ' + '[' * 1000 + '0' + ']' * 1000)
    elif mutation == 'boolean_choice':
        text = text.replace('"choice": 0', '"choice": false')
    elif mutation == 'string_choice':
        text = text.replace('"choice": 0', '"choice": "0"')
    elif mutation == 'float_choice':
        text = text.replace('"choice": 0', '"choice": 0.0')
    elif mutation == 'bad_uuid':
        text = text.replace(request['attempt_id'], 'x' * 36)
    elif mutation == 'invalid_unicode':
        text = text.replace('"choice": 0', '"choice": 0, "work": "\\ud800"')
    elif mutation == 'invalid_utf8':
        text = b'\xff'
    result = client.post('/v2/evaluations', content=text, headers={'Content-Type': 'application/json'})
    assert result.status_code == 422
    assert set(result.json()) == {'error'}
    assert h.balance(account)['available'] == 8
    with closing(h.db.connect()) as con:
        assert con.execute('SELECT COUNT(*) FROM evaluation_attempts').fetchone()[0] == 0


def test_authentication_device_gate_https_and_transport_limit(api):
    h, account, _, client = api
    payload = body()
    for header in ('', 'Bearer invented'):
        assert client.post('/v2/evaluations', json=payload, headers={'Authorization': header}).status_code == 401
    pending = client.post('/v2/evaluations', json=payload, headers={'X-Android-Id': B})
    assert pending.status_code == 409
    assert pending.json()['error'] == 'device_confirmation_required'
    assert client.post('http://127.0.0.1/v2/evaluations', json=payload).status_code == 400
    assert client.post('/v2/evaluations', content=b' ' * 16385).status_code == 413
    assert h.balance(account)['available'] == 8


def test_zero_hearts_http_pending_binds_request_and_resumes(api):
    h, account, _, client = api
    for _ in range(8):
        h.debit(account)
    request = body({'choice': 2})
    response = client.post('/v2/evaluations', json=request)
    assert response.status_code == 409
    assert response.json()['error'] == 'hearts_empty'
    assert response.json()['status'] == 'pending'
    assert not {'correct', 'receipt', 'result'} & response.json().keys()
    assert response.json()['hearts']['next_heart_at_ms'] == h.time[0] + HOUR_MS
    conflict = client.post('/v2/evaluations', json={**request, 'answer': {'choice': 0}})
    assert conflict.status_code == 409 and conflict.json()['error'] == 'attempt_conflict'
    h.time[0] += HOUR_MS
    accepted = client.post('/v2/evaluations', json=request)
    assert accepted.status_code == 200
    assert accepted.json()['receipt']['correct'] is True
    assert accepted.json()['hearts']['available'] == 1


def test_sqlite_constraint_failure_is_generic_503_and_atomic(api):
    h, account, _, client = api
    with closing(h.db.connect()) as con:
        con.execute("""CREATE TRIGGER simulated_failure BEFORE UPDATE ON evaluation_attempts
                    BEGIN SELECT RAISE(ABORT,'private-path-and-internal-secret'); END""")
    request = body()
    response = client.post('/v2/evaluations', json=request)
    assert response.status_code == 503
    assert response.json() == {'error': 'storage_unavailable'}
    assert response.headers['retry-after'] == '3'
    assert h.balance(account)['available'] == 8
    with closing(h.db.connect()) as con:
        assert con.execute('SELECT COUNT(*) FROM evaluation_results').fetchone()[0] == 0
        assert con.execute('SELECT COUNT(*) FROM evaluation_attempts').fetchone()[0] == 0
        con.execute('DROP TRIGGER simulated_failure')
    retry = client.post('/v2/evaluations', json=request)
    assert retry.status_code == 200 and retry.json()['hearts']['available'] == 7


def test_real_tls_actual_catalog_scrypt_and_receipt_after_server_restart(tmp_path):
    """Not TestClient: verified TLS and persisted state in two server processes."""
    state = tmp_path / 'state'
    state.mkdir()
    make_pki(state, secrets.token_bytes(32), [])
    token = secrets.token_urlsafe(48)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    write_private(state / 'config.json', json.dumps({
        'testing': True, 'project_id': '', 'host': '127.0.0.1', 'port': port,
        'testing_token_hash': hashlib.sha256(token.encode()).hexdigest(),
    }).encode())
    db = Database(state / 'servertec.db')
    store = AccountStore(db, AccountLedger(db).enroll)
    invitation = store.issue_invitation()['invitation']
    catalog = ExerciseCatalog.from_file(Path(__file__).with_name('rules-catalog.json'))
    rule = next(rule for rule in catalog.rules if rule.kind == 'multiple_choice')
    request = {'attempt_id': str(uuid4()), 'exercise_id': rule.id, 'exercise_version': rule.version,
               'answer': (rule.spec['correct_index'] + 1) % rule.spec['option_count']}
    env = os.environ.copy()
    env.pop('SSLKEYLOGFILE', None)
    command = [sys.executable, str(Path(__file__).with_name('manage.py')), 'serve', '--state', str(state)]
    session = None
    original_receipt = None
    with (state / 'server-test.log').open('wb') as log:
        for boot in range(2):
            child = subprocess.Popen(command, stdout=log, stderr=log, stdin=subprocess.DEVNULL, env=env)
            try:
                with httpx.Client(base_url=f'https://127.0.0.1:{port}',
                                  verify=private_tls_context(state / 'authority.pem'),
                                  trust_env=False, timeout=4) as client:
                    deadline = time.monotonic() + 20
                    while True:
                        assert child.poll() is None, (state / 'server-test.log').read_text()
                        try:
                            assert client.get('/health').status_code == 200
                            break
                        except httpx.TransportError:
                            assert time.monotonic() < deadline
                            time.sleep(0.05)
                    if boot == 0:
                        registered = client.post('/v2/auth/register', json={
                            'username': 'ActualTlsUser', 'password': PASS, 'invitation': invitation})
                        assert registered.status_code == 201
                        session = registered.json()['access_token']
                    client.headers.update({'Authorization': 'Bearer ' + session, 'X-Android-Id': A})
                    assert client.post('/v2/devices/prepare').json()['status'] == 'linked'
                    reply = client.post('/v2/evaluations', json=request)
                    assert reply.status_code == 200, reply.text
                    result = reply.json()
                    assert result['receipt']['correct'] is False
                    assert result['receipt']['charged_hearts'] == 1
                    assert result['hearts']['available'] == 7
                    assert result['replayed'] is bool(boot)
                    if boot == 0:
                        original_receipt = result['receipt']
                    else:
                        assert result['receipt'] == original_receipt
                    with closing(db.connect()) as con:
                        assert con.execute('SELECT COUNT(*) FROM evaluation_results').fetchone()[0] == 1
                        assert con.execute('SELECT COUNT(*) FROM evaluation_attempts WHERE result_hash IS NOT NULL').fetchone()[0] == 1
            finally:
                stop_owned_process(child)
    logged = (state / 'server-test.log').read_text()
    assert all(value not in logged for value in (session, token, invitation, PASS))
    with closing(db.connect()) as con:
        assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
