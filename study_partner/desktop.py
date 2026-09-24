"""Local macOS app lifecycle; never stop a process based on its port alone."""

import argparse
import contextlib
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from .paths import runtime_directory

ROOT = Path(__file__).resolve().parent.parent


class DesktopError(RuntimeError):
    pass


def output(args):
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


class Service:
    def __init__(self, root=ROOT, port=8765):
        self.root = Path(root).resolve()
        self.port = port
        self.bootstrap = os.getenv("STUDY_BUNDLE_BOOTSTRAP")
        runtime = runtime_directory() if root == ROOT or self.bootstrap else self.root / ".runtime"
        self.runtime = runtime / f"desktop-{port}"
        self.python = Path(sys.executable) if self.bootstrap else self.root / ".venv/bin/python"
        self.command = (
            [str(self.python), "-I", "-B", self.bootstrap, "serve", "--port", str(port)]
            if self.bootstrap else
            [str(self.python), "-m", "uvicorn", "study_partner.app:app", "--host",
             "127.0.0.1", "--port", str(port), "--no-access-log",
             "--timeout-graceful-shutdown", "10"]
        )
        self.state = self.runtime / "service.json"
        self.url = f"http://127.0.0.1:{port}/"

    @contextlib.contextmanager
    def locked(self):
        self.runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.runtime / "control.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def listeners(self):
        text = output(["/usr/sbin/lsof", "-nP", f"-iTCP:{self.port}", "-sTCP:LISTEN", "-t"])
        return sorted({int(line) for line in text.splitlines() if line.isdigit()})

    def identity(self, pid):
        if not isinstance(pid, int) or pid <= 1:
            return None
        started = output(["/bin/ps", "-p", str(pid), "-o", "lstart="])
        command = output(["/bin/ps", "-p", str(pid), "-o", "command="])
        cwd_lines = output(["/usr/sbin/lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"])
        cwd = next((line[1:] for line in cwd_lines.splitlines() if line.startswith("n")), "")
        if not started or not cwd or Path(cwd).resolve() != self.root:
            return None
        base = f"study_partner.app:app --host 127.0.0.1 --port {self.port} --no-access-log"
        allowed = {" ".join(self.command)}
        for python in ("python", "python3", "python3.12"):
            executable = self.root / ".venv" / "bin" / python
            for module in ("-m uvicorn", str(self.root / ".venv/bin/uvicorn")):
                for suffix in ("", " --timeout-graceful-shutdown 10"):
                    allowed.add(f"{executable} {module} {base}{suffix}")
        if command not in allowed:
            return None
        return {"pid": pid, "started": started, "command": command, "cwd": str(self.root)}

    def discover(self):
        listeners = self.listeners()
        if not listeners:
            return None
        identities = [self.identity(pid) for pid in listeners]
        if len(identities) != 1 or identities[0] is None:
            raise DesktopError(f"連接埠 {self.port} 已被其他程式使用，未變更或關閉該程式。")
        return identities[0]

    def ready(self):
        try:
            with urlopen(self.url, timeout=1) as response:
                return response.status == 200
        except (OSError, URLError):
            return False

    def remember(self, identity):
        temporary = self.state.with_suffix(".tmp")
        temporary.write_text(json.dumps(identity), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(self.state)

    def start(self):
        with self.locked():
            identity = self.discover()
            if identity:
                if not self.ready():
                    raise DesktopError("本專案服務正在啟動或暫時無法回應，請稍後重新開啟 App。")
                self.remember(identity)
                return "已接手正在執行的伴讀服務"
            python = self.python
            if not python.exists():
                raise DesktopError("找不到專案執行環境，請重新執行 Install App.command。")
            with (self.runtime / "server.log").open("ab") as log:
                proc = subprocess.Popen(
                    self.command,
                    cwd=self.root, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                    start_new_session=True,
                )
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise DesktopError(f"服務啟動失敗，請查看 {self.runtime / 'server.log'}。")
                identity = self.identity(proc.pid)
                if identity and self.ready() and self.listeners() == [proc.pid]:
                    self.remember(identity)
                    return "伴讀服務已啟動"
                time.sleep(0.15)
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired as error:
                # Keep a verifiable record so a subsequent stop can finish cleanup.
                identity = self.identity(proc.pid)
                if identity:
                    self.remember(identity)
                raise DesktopError("啟動逾時，服務尚在結束中，請稍後再試。") from error
            raise DesktopError("服務啟動逾時，已停止本次啟動。")

    def stop(self):
        with self.locked():
            if not self.state.exists():
                return "此 App 尚未啟動服務"
            try:
                expected = json.loads(self.state.read_text(encoding="utf-8"))
                pid = expected["pid"]
            except (ValueError, KeyError, TypeError) as error:
                raise DesktopError("服務紀錄無法核對，未關閉任何程式。") from error
            if self.identity(pid) != expected:
                self.state.unlink(missing_ok=True)
                return "原本的伴讀服務已停止，未變更其他程式"
            os.kill(pid, signal.SIGTERM)
            deadline = time.monotonic() + 22
            while time.monotonic() < deadline:
                if self.identity(pid) != expected:
                    self.state.unlink(missing_ok=True)
                    return "伴讀服務已關閉"
                time.sleep(0.15)
            raise DesktopError("服務仍在結束處理，App 尚未退出；請稍後再按退出。")

    def status(self):
        with self.locked():
            return "running" if self.discover() and self.ready() else "stopped"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "stop", "status"])
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("App 啟動器僅支援 macOS。")
    try:
        print(getattr(Service(port=args.port), args.action)())
    except (DesktopError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
