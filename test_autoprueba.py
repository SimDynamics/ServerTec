import json
import os
from pathlib import Path
import ssl
import subprocess
import sys

import pytest

from autoprueba import (SelfCheckError, cleanup_disposable_directory, disposable_directory,
                       private_tls_context, run_selfcheck, stop_owned_process)
from manage import make_pki


def test_selfcheck_end_to_end_isolated_state_and_no_production_mutation(tmp_path, monkeypatch):
    production = tmp_path / 'profile' / 'ServerTec' / 'state'
    production.mkdir(parents=True)
    sentinel = production / 'servertec.db'
    sentinel.write_bytes(b'REAL_DATA_NOT_SQLITE_MUST_NOT_BE_OPENED')
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'profile'))
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    result = run_selfcheck()
    assert result['status'] == 'ok'
    assert result['checks_passed'] == 9
    assert result['temporary_state_removed']
    assert not result['production_state_modified']
    after = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert before == after


def test_tls_context_cannot_turn_off_hostname_or_ca_checks_or_log_session_keys(tmp_path, monkeypatch):
    make_pki(tmp_path, b'another-disposable-test-password', [])
    keylog = tmp_path / 'forbidden-ssl-keylog.txt'
    monkeypatch.setenv('SSLKEYLOGFILE', str(keylog))
    context = private_tls_context(tmp_path / 'authority.pem')
    assert context.check_hostname
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
    assert context.keylog_filename is None
    assert not keylog.exists()


def test_invalid_timeout_rejected_without_starting_any_process():
    for value in (0, -1, 121):
        with pytest.raises(SelfCheckError):
            run_selfcheck(timeout=value)


def test_own_child_can_be_stopped_without_terminating_other_processes():
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(90)'])
    other = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(90)'])
    try:
        stop_owned_process(child)
        assert child.poll() is not None
        assert other.poll() is None
        stop_owned_process(child)  # idempotent cleanup
    finally:
        stop_owned_process(other)


def test_selfcheck_cleanup_after_mid_request_failure(monkeypatch):
    import autoprueba
    import tempfile
    saved = []
    original = tempfile.TemporaryDirectory
    class TrackingTemporaryDirectory(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            saved.append(Path(self.name))
    monkeypatch.setattr(autoprueba.tempfile, 'TemporaryDirectory', TrackingTemporaryDirectory)
    original_ensure = autoprueba.ensure
    def fail_at_stage(value, code):
        if code == 'routes_not_isolated':
            raise SelfCheckError('simulated_stop')
        return original_ensure(value, code)
    monkeypatch.setattr(autoprueba, 'ensure', fail_at_stage)
    with pytest.raises(SelfCheckError, match='simulated_stop'):
        autoprueba.run_selfcheck()
    assert saved and all(not p.exists() for p in saved)



def test_temporary_cleanup_retries_windows_sharing_violation_only(monkeypatch):
    import autoprueba
    import tempfile
    original = tempfile.TemporaryDirectory
    instances = []

    class SharingViolationOnce(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.attempts = 0
            instances.append(self)

        def cleanup(self):
            self.attempts += 1
            if self.attempts == 1:
                error = PermissionError(13, 'transient sharing violation')
                error.winerror = 32
                raise error
            super().cleanup()

    monkeypatch.setattr(autoprueba.tempfile, 'TemporaryDirectory', SharingViolationOnce)
    with disposable_directory() as folder:
        marker = Path(folder) / 'owned-test-data'
        marker.write_text('disposable')
    assert len(instances) == 1
    assert instances[0].attempts == 2
    assert not Path(instances[0].name).exists()

