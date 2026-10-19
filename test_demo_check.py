"""Real TLS/process regression checks; all identities and listeners are disposable."""
from contextlib import contextmanager
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time

import pytest

from demo_check import https_get, tls_context, verify_demo
from demo_pki import prepare_demo


ROOT = Path(__file__).resolve().parent


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def stop_child(child):
    if child.poll() is None:
        if os.name == 'nt':
            # The Windows venv launcher owns a second Python process. Terminating
            # just that launcher would leave its TLS listener running. This tree
            # is rooted in OUR Popen handle, never a process found by name/port.
            result = subprocess.run(['taskkill.exe', '/F', '/T', '/PID', str(child.pid)],
                                    capture_output=True, timeout=10)
            if result.returncode != 0 and child.poll() is None:
                raise RuntimeError('Could not stop our own demo process tree')
            child.wait(timeout=8)
            return
        child.terminate()
        try:
            child.wait(timeout=8)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)


def command(directory, port):
    return [sys.executable, str(ROOT / 'demo_web.py'), 'serve', '--enable-demo',
            '--host', '127.0.0.1', '--port', str(port),
            '--cert', str(directory / 'runtime' / 'server.pem'),
            '--key', str(directory / 'runtime' / 'server-key.pem')]


@contextmanager
def running_demo(directory, port):
    child = subprocess.Popen(command(directory, port), cwd=ROOT,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 15
        while True:
            assert child.poll() is None, 'Our own demo child stopped before readiness'
            try:
                if https_get('127.0.0.1', port, '/', directory / 'public' / 'authority.pem')[0] == 200:
                    break
            except OSError:
                pass
            assert time.monotonic() < deadline, 'Our own demo child never became ready'
            time.sleep(0.05)
        yield child
    finally:
        stop_child(child)


def test_real_tls_menu_allowlist_rejections_and_owned_process_restart(tmp_path):
    identity = tmp_path / 'identity'
    prepare_demo(identity, None)
    other_identity = tmp_path / 'other-identity'
    prepare_demo(other_identity, None)
    port = free_port()
    with socket.socket() as unrelated_listener:
        unrelated_listener.bind(('127.0.0.1', 0))
        unrelated_listener.listen(1)
        unrelated_port = unrelated_listener.getsockname()[1]
        with running_demo(identity, port):
            first = verify_demo(identity, '127.0.0.1', port)
            assert first['dns_or_chrome_verified'] is False
            assert len(first['checks']) == 4
            with pytest.raises(ssl.SSLCertVerificationError):
                https_get('127.0.0.1', port, '/', other_identity / 'public' / 'authority.pem')
            # An incorrect or absent system CA is never silently accepted either.
            with socket.create_connection(('127.0.0.1', port), timeout=2) as raw:
                with pytest.raises(ssl.SSLCertVerificationError):
                    with ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).wrap_socket(
                            raw, server_hostname='learngraphicsprogramming.dynamics'):
                        pytest.fail('Untrusted demo authority accepted')
        with pytest.raises(OSError):
            with socket.create_connection(('127.0.0.1', port), timeout=1):
                pytest.fail('Our demo listener survived its own process shutdown')
        with running_demo(identity, port):
            second = verify_demo(identity, '127.0.0.1', port)
            assert first['run_id'] != second['run_id']
        with socket.create_connection(('127.0.0.1', unrelated_port), timeout=1):
            accepted, _ = unrelated_listener.accept()
            accepted.close()


def test_occupied_port_fails_without_stopping_or_replacing_owner(tmp_path):
    identity = tmp_path / 'identity'
    prepare_demo(identity, None)
    with socket.socket() as unrelated_listener:
        unrelated_listener.bind(('127.0.0.1', 0))
        unrelated_listener.listen(1)
        port = unrelated_listener.getsockname()[1]
        result = subprocess.run(command(identity, port), cwd=ROOT, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=15)
        assert result.returncode != 0
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            accepted, _ = unrelated_listener.accept()
            accepted.close()


def test_verifier_never_enables_session_key_export(tmp_path, monkeypatch):
    identity = tmp_path / 'identity'
    prepare_demo(identity, None)
    keylog = tmp_path / 'must-not-export-session-keys.log'
    monkeypatch.setenv('SSLKEYLOGFILE', str(keylog))
    context = tls_context(identity / 'public' / 'authority.pem')
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    assert context.keylog_filename is None
    assert not keylog.exists()
