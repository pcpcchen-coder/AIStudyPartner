from pathlib import Path

import pytest

from study_partner import desktop
from study_partner.codex_bridge import CodexBridge
from study_partner.paths import runtime_directory


def test_external_runtime_is_shared_by_bridge_and_launcher(tmp_path, monkeypatch):
    runtime = tmp_path / 'Application Support' / 'AIStudyPartner'
    monkeypatch.setenv('STUDY_RUNTIME_DIR', str(runtime))
    monkeypatch.setenv('STUDY_BUNDLE_BOOTSTRAP', str(tmp_path / 'Moved App/bootstrap.py'))
    service = desktop.Service(port=8877)
    assert runtime_directory() == runtime
    assert CodexBridge().runtime == runtime
    assert service.runtime == runtime / 'desktop-8877'
    assert service.command[1:3] == ['-I', '-B']
    assert service.command[-3:] == ['serve', '--port', '8877']


def test_relative_runtime_is_rejected(monkeypatch):
    monkeypatch.setenv('STUDY_RUNTIME_DIR', 'relative-data')
    with pytest.raises(ValueError, match='absolute'):
        runtime_directory()


def test_bundle_identity_supports_spaces_and_rejects_other_bundle(tmp_path, monkeypatch):
    monkeypatch.setenv('STUDY_RUNTIME_DIR', str(tmp_path / 'data'))
    bootstrap = tmp_path / 'Moved App/Contents/Resources/bootstrap.py'
    monkeypatch.setenv('STUDY_BUNDLE_BOOTSTRAP', str(bootstrap))
    service = desktop.Service(root=tmp_path / 'Moved App/Contents/Resources/app', port=8877)
    command = ' '.join(service.command)

    def inspect(args):
        if args[0] == '/usr/sbin/lsof':
            return f'p42\nn{service.root}'
        return 'test start time' if args[-1] == 'lstart=' else command

    monkeypatch.setattr(desktop, 'output', inspect)
    assert service.identity(42)['command'] == command
    command = command.replace(str(bootstrap), str(Path('/other/bootstrap.py')))
    assert service.identity(42) is None
