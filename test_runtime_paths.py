"""Data-root and initialization safety checks; all files here are disposable.

The PowerShell assertions are static checks, not a substitute for Windows QA.
"""
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pytest

import manage


def test_windows_default_is_on_d_regardless_of_profile_or_working_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(manage, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'different-profile'))
    monkeypatch.chdir(tmp_path)
    state = PureWindowsPath(str(manage.state_default()))
    assert state == PureWindowsPath(r'D:\Projects\ServerTec\state')
    assert state.is_absolute()
    assert list(tmp_path.iterdir()) == []


def test_non_windows_default_remains_outside_code(tmp_path, monkeypatch):
    monkeypatch.setattr(manage, 'sys', SimpleNamespace(platform='linux'))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    assert manage.state_default() == tmp_path / 'ServerTec' / 'state'


def test_preflight_never_creates_or_moves_anything(tmp_path, monkeypatch):
    monkeypatch.delenv('LOCALAPPDATA', raising=False)
    target = tmp_path / 'new-data' / 'state'
    manage.check_initialization_target(target)
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('is_directory', [True, False])
def test_preflight_preserves_existing_target(tmp_path, monkeypatch, is_directory):
    monkeypatch.delenv('LOCALAPPDATA', raising=False)
    target = tmp_path / 'state'
    if is_directory:
        target.mkdir()
        sentinel = target / 'servertec.db'
    else:
        sentinel = target
    sentinel.write_bytes(b'EXISTING_PRIVATE_DATA')
    with pytest.raises(ValueError, match='ya contiene datos'):
        manage.check_initialization_target(target)
    assert sentinel.read_bytes() == b'EXISTING_PRIVATE_DATA'


def test_preflight_refuses_new_identity_when_legacy_state_exists(tmp_path, monkeypatch):
    profile = tmp_path / 'profile'
    legacy = profile / 'ServerTec' / 'state'
    legacy.mkdir(parents=True)
    sentinel = legacy / 'device-hmac.key'
    sentinel.write_bytes(b'EXISTING_KEY_DO_NOT_REPLACE')
    monkeypatch.setenv('LOCALAPPDATA', str(profile))
    new_target = tmp_path / 'data-on-d' / 'state'
    with pytest.raises(ValueError, match='Existe estado anterior'):
        manage.check_initialization_target(new_target)
    assert sentinel.read_bytes() == b'EXISTING_KEY_DO_NOT_REPLACE'
    assert not new_target.exists()


def test_preflight_allows_empty_legacy_directory(tmp_path, monkeypatch):
    legacy = tmp_path / 'profile' / 'ServerTec' / 'state'
    legacy.mkdir(parents=True)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'profile'))
    target = tmp_path / 'data-on-d' / 'state'
    manage.check_initialization_target(target)
    assert legacy.is_dir() and not target.exists()


def test_preflight_refuses_data_under_source_without_creating_it(monkeypatch):
    monkeypatch.delenv('LOCALAPPDATA', raising=False)
    target = Path(manage.__file__).resolve().parent / 'must-not-create-state'
    assert not target.exists()
    with pytest.raises(ValueError, match='FUERA del repositorio'):
        manage.check_initialization_target(target)
    assert not target.exists()


def test_cli_check_init_only_checks_without_requesting_secrets(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv('LOCALAPPDATA', raising=False)
    target = tmp_path / 'state'
    monkeypatch.setattr(manage.sys, 'argv', ['manage.py', 'check-init', '--state', str(target)])
    monkeypatch.setattr(manage.getpass, 'getpass', lambda *_: pytest.fail('Unexpected password request'))
    manage.main()
    assert 'No se creo ni modifico' in capsys.readouterr().out
    assert not target.exists()


def test_cli_init_stops_before_prompt_when_legacy_state_exists(tmp_path, monkeypatch):
    legacy = tmp_path / 'profile' / 'ServerTec' / 'state'
    legacy.mkdir(parents=True)
    (legacy / 'servertec.db').write_bytes(b'KEEP')
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'profile'))
    target = tmp_path / 'new-state'
    monkeypatch.setattr(manage.sys, 'argv', ['manage.py', 'init', '--state', str(target)])
    monkeypatch.setattr(manage.getpass, 'getpass', lambda *_: pytest.fail('Unexpected password request'))
    with pytest.raises(ValueError, match='Existe estado anterior'):
        manage.main()
    assert not target.exists()


def test_powershell_paths_and_preflight_match_python_contract():
    root = Path(__file__).resolve().parent
    launcher = (root / 'ServerTec.ps1').read_text(encoding='utf-8')
    diagnostic = (root / 'Diagnostico-Red.ps1').read_text(encoding='utf-8')
    assert "$root = $PSScriptRoot" in launcher
    assert r"$dataRoot = 'D:\Projects\ServerTec'" in launcher
    assert "$state = Join-Path $dataRoot 'state'" in launcher
    assert "$reports = Join-Path $dataRoot 'reports'" in launcher
    assert '-OutputDirectory $reports' in launcher
    assert r"'D:\Projects\ServerTec\reports'" in diagnostic
    assert launcher.index("'check-init'") < launcher.index('New-Item -ItemType Directory -Path $state')
    assert "if ($Accion -eq 'Rutas')" in launcher
