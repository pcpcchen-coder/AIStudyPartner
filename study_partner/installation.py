"""Replace or uninstall our installed apps without deleting account or study data."""

import argparse
import datetime
import os
import plistlib
import shutil
import subprocess
import tempfile
from pathlib import Path

IDS = {'local.aistudypartner.desktop', 'local.aistudypartner.standalone'}
LSREGISTER = '/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister'


def app_id(path):
    try:
        return plistlib.loads((path / 'Contents/Info.plist').read_bytes()).get('CFBundleIdentifier')
    except (OSError, ValueError, plistlib.InvalidFileException):
        return None


def register(path, remove=False):
    subprocess.run([LSREGISTER, '-u' if remove else '-f', str(path)],
                   capture_output=True, check=not remove)


def installed_apps(directories):
    return [path for directory in directories if directory.exists()
            for path in directory.glob('*.app') if not path.is_symlink() and app_id(path) in IDS]


def verify(app):
    if app.is_symlink() or app_id(app) not in IDS:
        raise ValueError('這不是可安裝的 AIStudyPartner App，未變更任何程式。')
    subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(app)], check=True)


def ensure_stopped(apps):
    commands = subprocess.check_output(['/bin/ps', '-axo', 'command='], text=True).splitlines()
    for app in apps:
        prefix = str(app / 'Contents') + '/'
        if any(command.strip().startswith(prefix) for command in commands):
            raise ValueError('請先從伴讀 App 選單退出並關閉服務，再執行安裝或移除。')
        if not os.access(app.parent, os.W_OK):
            raise ValueError(f'無法替換 {app}，請由有權限的使用者移除舊版後再安裝。')


def backup(app, folder):
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.UTC).strftime('%Y%m%d-%H%M%S-%f')
    target = folder / f'AIStudyPartner-{stamp}.zip'
    subprocess.run(['/usr/bin/ditto', '-c', '-k', '--sequesterRsrc', '--keepParent',
                    str(app), str(target)], check=True)
    return target


def install(source, directories=None, destination=None, backup_dir=None):
    source = Path(source).resolve()
    directories = directories or [Path.home() / 'Applications', Path('/Applications')]
    existing = installed_apps(directories)
    destination = destination or next((app for app in existing if app.name == 'AIStudyPartner.app'),
                                     directories[0] / 'AIStudyPartner.app')
    if source == destination.resolve():
        raise ValueError('此 App 已在安裝位置，請從新下載的安裝包執行更新。')
    if (destination.exists() or destination.is_symlink()) and destination not in existing:
        raise ValueError('安裝位置有其他程式，未覆蓋。')
    verify(source)
    ensure_stopped(existing)
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup_dir = backup_dir or Path.home() / 'Library/Application Support/AIStudyPartner/installer-backups'
    # Staging and rollback remain on the destination filesystem for atomic renames.
    with tempfile.TemporaryDirectory(prefix='.AIStudyPartner-install-', suffix='.noindex',
                                     dir=destination.parent) as folder:
        stage = Path(folder) / 'new.app'
        moved = []
        published = False
        try:
            subprocess.run(['/usr/bin/ditto', '--qtn', str(source), str(stage)], check=True)
            # Keep quarantine/security metadata; discard Finder-only metadata.
            for attribute in ('com.apple.ResourceFork', 'com.apple.FinderInfo'):
                subprocess.run(['/usr/bin/xattr', '-r', '-d', attribute, str(stage)],
                               capture_output=True, check=False)
            verify(stage)
            # Finish every backup before modifying any installed App.
            for old in existing:
                backup(old, backup_dir)
            for index, old in enumerate(existing):
                register(old, remove=True)
                retired = Path(folder) / f'old-{index}.app'
                old.rename(retired)
                moved.append((old, retired))
            stage.rename(destination)
            published = True
            register(destination)
        except Exception:
            if published and destination.exists():
                register(destination, remove=True)
                shutil.rmtree(destination)
            for old, retired in reversed(moved):
                retired.rename(old)
            for old in existing:
                if old.exists():
                    register(old)
            raise
        finally:
            register(stage, remove=True)
            for _, retired in moved:
                register(retired, remove=True)
    return destination


def uninstall(directories=None, backup_dir=None):
    directories = directories or [Path.home() / 'Applications', Path('/Applications')]
    apps = installed_apps(directories)
    ensure_stopped(apps)
    backup_dir = backup_dir or Path.home() / 'Library/Application Support/AIStudyPartner/installer-backups'
    for app in apps:
        backup(app, backup_dir)
    for app in apps:
        register(app, remove=True)
        shutil.rmtree(app)
    return len(apps)


def main(source):
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['install', 'uninstall'])
    args = parser.parse_args()
    try:
        if args.action == 'install':
            target = install(source)
            print(f'已安裝／更新：{target}\n舊 App 已移除並備份為 ZIP，登入與學習資料保留。')
        else:
            count = uninstall()
            print(f'已移除 {count} 份伴讀 App；登入與學習資料保留，App 備份為 ZIP。')
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(f'未完成：{error}') from error
