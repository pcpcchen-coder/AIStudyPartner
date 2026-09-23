import json
import signal
from unittest.mock import Mock

import pytest

from study_partner import desktop
from study_partner.desktop import DesktopError, Service


@pytest.fixture
def service(tmp_path):
    return Service(tmp_path, port=8877)


def identity(service, pid=42):
    return {"pid": pid, "started": "Wed Sep 23 20:40:18 2026", "cwd": str(service.root),
            "command": f"{service.root}/.venv/bin/python -m uvicorn study_partner.app:app "
                       "--host 127.0.0.1 --port 8877 --no-access-log --timeout-graceful-shutdown 10"}


@pytest.mark.parametrize("changed", [None, "cwd", "command", "port"])
def test_process_identity_requires_repo_command_and_port(service, monkeypatch, changed):
    expected = identity(service)
    cwd = str(service.root) if changed != "cwd" else "/another/repository"
    command = expected["command"]
    if changed == "command":
        command = "/usr/bin/python unrelated.py"
    if changed == "port":
        command = command.replace("8877", "8765")

    def inspect(args):
        if args[0] == "/usr/sbin/lsof":
            return f"p42\nn{cwd}"
        return expected["started"] if args[-1] == "lstart=" else command

    monkeypatch.setattr(desktop, "output", inspect)
    assert service.identity(42) == (expected if changed is None else None)


def test_unrelated_listener_is_never_adopted(service, monkeypatch):
    monkeypatch.setattr(service, "listeners", lambda: [42])
    monkeypatch.setattr(service, "identity", lambda pid: None)
    with pytest.raises(DesktopError, match="其他程式"):
        service.start()
    assert not service.state.exists()


def test_start_adopts_same_repo_without_restarting(service, monkeypatch):
    expected = identity(service)
    monkeypatch.setattr(service, "discover", lambda: expected)
    monkeypatch.setattr(service, "ready", lambda: True)
    spawn = Mock()
    monkeypatch.setattr(desktop.subprocess, "Popen", spawn)
    assert "接手" in service.start()
    spawn.assert_not_called()
    assert json.loads(service.state.read_text()) == expected


def test_start_creates_one_detached_server_with_shutdown_deadline(service, monkeypatch):
    expected = identity(service)
    (service.root / ".venv/bin").mkdir(parents=True)
    (service.root / ".venv/bin/python").touch()
    monkeypatch.setattr(service, "discover", lambda: None)
    monkeypatch.setattr(service, "identity", lambda pid: expected)
    monkeypatch.setattr(service, "ready", lambda: True)
    monkeypatch.setattr(service, "listeners", lambda: [42])
    process = Mock(pid=42)
    process.poll.return_value = None
    spawn = Mock(return_value=process)
    monkeypatch.setattr(desktop.subprocess, "Popen", spawn)
    assert "已啟動" in service.start()
    assert spawn.call_args.args[0][-2:] == ["--timeout-graceful-shutdown", "10"]
    assert spawn.call_args.kwargs["start_new_session"] is True
    assert json.loads(service.state.read_text()) == expected


def test_stop_checks_birth_identity_before_sending_signal(service, monkeypatch):
    expected = identity(service)
    with service.locked():
        service.remember(expected)
    monkeypatch.setattr(service, "identity", Mock(side_effect=[expected, None]))
    kill = Mock()
    monkeypatch.setattr(desktop.os, "kill", kill)
    assert "已關閉" in service.stop()
    kill.assert_called_once_with(42, signal.SIGTERM)
    assert not service.state.exists()


def test_reused_pid_is_not_killed(service, monkeypatch):
    expected = identity(service)
    with service.locked():
        service.remember(expected)
    monkeypatch.setattr(service, "identity", lambda pid: {**expected, "started": "a later time"})
    kill = Mock()
    monkeypatch.setattr(desktop.os, "kill", kill)
    assert "未變更其他程式" in service.stop()
    kill.assert_not_called()


def test_broken_record_never_signals_a_process(service, monkeypatch):
    with service.locked():
        service.state.write_text("not json")
    kill = Mock()
    monkeypatch.setattr(desktop.os, "kill", kill)
    with pytest.raises(DesktopError, match="無法核對"):
        service.stop()
    kill.assert_not_called()
