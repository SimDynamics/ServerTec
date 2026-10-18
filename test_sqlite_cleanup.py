"""Regression: SQLite handles must close before temporary-state removal."""
from pathlib import Path

import pytest

from autoprueba import SelfCheckError, run_selfcheck


@pytest.mark.parametrize('failure_stage', [None, 'database_integrity_failed', 'portable_settings_not_persisted'])
def test_all_sqlite_handles_close_before_cleanup_even_on_failure(monkeypatch, failure_stage):
    """Retain strong references so GC cannot hide the Windows file-lock regression."""
    import autoprueba
    import sqlite3
    connections = []
    cleaned = []
    connect = sqlite3.connect
    cleanup = autoprueba.cleanup_disposable_directory
    original_ensure = autoprueba.ensure

    class TrackedConnection(sqlite3.Connection):
        closed_explicitly = False

        def close(self):
            super().close()
            self.closed_explicitly = True

    def tracked_connect(*args, **kwargs):
        kwargs['factory'] = TrackedConnection
        connection = connect(*args, **kwargs)
        connections.append(connection)
        return connection

    def check_cleanup(temporary):
        assert connections and all(c.closed_explicitly for c in connections), 'unclosed SQLite handle before cleanup'
        cleanup(temporary)
        cleaned.append(Path(temporary.name))

    def fail_at_stage(value, code):
        if code == failure_stage:
            raise SelfCheckError('simulated_sqlite_check_failure')
        original_ensure(value, code)

    monkeypatch.setattr(autoprueba.sqlite3, 'connect', tracked_connect)
    monkeypatch.setattr(autoprueba, 'cleanup_disposable_directory', check_cleanup)
    monkeypatch.setattr(autoprueba, 'ensure', fail_at_stage)
    try:
        if failure_stage is None:
            assert run_selfcheck()['checks_passed'] == 9
        else:
            with pytest.raises(SelfCheckError, match='simulated_sqlite_check_failure'):
                run_selfcheck()
        assert cleaned and all(not p.exists() for p in cleaned)
    finally:
        for connection in connections:
            connection.close()
