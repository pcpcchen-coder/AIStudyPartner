import plistlib
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import macos_lifecycle
from study_partner import installation as installer


def app(path, ident='local.aistudypartner.standalone', version='new'):
    (path / 'Contents').mkdir(parents=True)
    (path / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': ident}))
    (path / 'version').write_text(version)
    return path


@pytest.fixture
def environment(tmp_path, monkeypatch):
    source = app(tmp_path / 'download/AIStudyPartner.app')
    dirs = [tmp_path / 'user-apps', tmp_path / 'system-apps']
    for directory in dirs:
        directory.mkdir()
    backups = tmp_path / 'data/backups'
    data = tmp_path / 'data/account-placeholder'
    data.parent.mkdir(exist_ok=True)
    data.write_text('keep me')
    registered = []
    monkeypatch.setattr(installer, 'register', lambda p, remove=False: registered.append((p, remove)))
    monkeypatch.setattr(installer, 'verify', lambda p: None)
    monkeypatch.setattr(installer, 'ensure_stopped', lambda p: None)

    def backup(p, folder):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f'{p.parent.name}-{p.name}.zip').write_text((p / 'version').read_text())

    def run(args, **kwargs):
        if args[0] == '/usr/bin/ditto':
            shutil.copytree(args[-2], args[-1])
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(installer, 'backup', backup)
    monkeypatch.setattr(installer.subprocess, 'run', run)
    return source, dirs, backups, data, registered


def test_install_replaces_both_old_identities_and_repeated_install_stays_single(environment):
    source, dirs, backups, data, registered = environment
    destination = app(dirs[0] / 'AIStudyPartner.app', 'local.aistudypartner.desktop', 'old')
    duplicate = app(dirs[1] / 'AIStudyPartner Copy.app', version='duplicate')
    foreign = app(dirs[0] / 'Other.app', 'other.app', 'unrelated')
    for _ in range(2):
        assert installer.install(source, dirs, backup_dir=backups) == destination
        assert installer.installed_apps(dirs) == [destination]
        assert (destination / 'version').read_text() == 'new'
        assert data.read_text() == 'keep me'
    assert not duplicate.exists()
    assert foreign.exists()
    assert len(list(backups.glob('*.zip'))) == 2
    assert (duplicate, True) in registered


def test_failed_publish_restores_previous_app(environment, monkeypatch):
    source, dirs, backups, data, _ = environment
    destination = app(dirs[0] / 'AIStudyPartner.app', version='old')
    failed = False

    def register(path, remove=False):
        nonlocal failed
        if path == destination and not remove and not failed:
            failed = True
            raise OSError('test registration failure')

    monkeypatch.setattr(installer, 'register', register)
    with pytest.raises(OSError):
        installer.install(source, dirs, backup_dir=backups)
    assert (destination / 'version').read_text() == 'old'
    assert data.read_text() == 'keep me'


def test_uninstall_only_our_apps_and_keeps_data(environment):
    _, dirs, backups, data, _ = environment
    app(dirs[0] / 'AIStudyPartner.app', version='old')
    other = app(dirs[0] / 'Other.app', 'other.app')
    assert installer.uninstall(dirs, backups) == 1
    assert installer.uninstall(dirs, backups) == 0
    assert other.exists() and data.read_text() == 'keep me'
    assert len(list(backups.glob('*.zip'))) == 1


def test_foreign_destination_is_not_replaced(environment):
    source, dirs, backups, _, _ = environment
    destination = app(dirs[0] / 'AIStudyPartner.app', 'foreign.app', 'keep')
    with pytest.raises(ValueError, match='其他程式'):
        installer.install(source, dirs, backup_dir=backups)
    assert (destination / 'version').read_text() == 'keep'


def test_running_app_blocks_update(tmp_path, monkeypatch):
    target = app(tmp_path / 'AIStudyPartner.app')
    monkeypatch.setattr(installer.subprocess, 'check_output', lambda *a, **k: str(target / 'Contents/MacOS/applet'))
    with pytest.raises(ValueError, match='先從伴讀 App'):
        installer.ensure_stopped([target])


def test_temporary_registration_cleanup_on_failure(monkeypatch):
    removed = []
    monkeypatch.setattr(macos_lifecycle, 'unregister', removed.append)
    with pytest.raises(ValueError), macos_lifecycle.temporary_apps('test-study-') as root:
        stale = root / 'moved-away.app'
        present = app(root / 'present.app')
        outside = Path('/unrelated/Other.app')
        monkeypatch.setattr(macos_lifecycle, 'registered_paths', lambda: [stale, outside])
        raise ValueError('simulate failed build')
    assert stale in removed and present in removed and outside not in removed
    assert not root.exists()
