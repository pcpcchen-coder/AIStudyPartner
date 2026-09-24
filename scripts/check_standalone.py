"""Exercise a relocated bundle without developer tools, credentials or model inference."""

import argparse
import json
import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def check(app):
    with tempfile.TemporaryDirectory(prefix="Study Partner relocation ") as folder:
        root = Path(folder).resolve()
        moved = root / "Moved App/AIStudyPartner.app"
        shutil.copytree(app, moved, symlinks=True)
        resources = moved / "Contents/Resources"
        for path in moved.rglob("*"):
            if path.is_symlink():
                assert path.resolve().is_relative_to(moved), f"External symlink: {path}"
        assert not list(resources.rglob("auth.json"))
        assert not list(resources.rglob(".runtime"))
        env = {key: value for key, value in os.environ.items()
               if key in {"HOME", "USER", "LOGNAME", "TMPDIR", "LANG"}}
        env.update(PATH="/usr/bin:/bin:/usr/sbin:/sbin", STUDY_RUNTIME_DIR=str(root / "Fresh Data"))
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        control = resources / "app-control.sh"

        def command(action):
            result = subprocess.run([str(control), action, "--port", str(port)], env=env,
                                    cwd=root, check=True, capture_output=True, text=True, timeout=50)
            return result.stdout.strip()

        details = json.loads(command("selfcheck"))
        assert details["model"] == "gpt-6-astra"
        assert details["codex"] == "codex-cli 0.156.1"
        assert Path(details["executable"]).is_relative_to(resources)
        url = f"http://127.0.0.1:{port}"

        def request(path, token=None):
            headers = {"Content-Type": "application/json", "X-Study-Token": token} if token else {}
            query = Request(url + path, data=b"{}" if token else None, headers=headers)
            with urlopen(query, timeout=30) as response:
                return json.load(response)

        try:
            assert "已啟動" in command("start")
            assert command("status") == "running"
            state = root / f"Fresh Data/desktop-{port}/service.json"
            first = json.loads(state.read_text())
            assert "接手" in command("start")
            assert json.loads(state.read_text()) == first
            config = request("/api/config")
            assert not config["ready"]
            assert {model["id"] for model in config["models"]} == {"gpt-6-astra", "gpt-6-sol", "gpt-6-luna"}
            login = request("/api/auth/login", config["token"])
            assert urlparse(login["auth_url"]).hostname in {"auth.openai.com", "chatgpt.com"}
            assert request("/api/auth/logout", config["token"])["logged_out"]
            assert request("/api/demo/%E6%95%B8%E5%AD%B8")["source"] == "demo"
            assert "已關閉" in command("stop")
            assert command("status") == "stopped"
            assert not state.exists()
            assert "已啟動" in command("start")
            assert "已關閉" in command("stop")
            subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(moved)], check=True)
            print(json.dumps({"result": "passed", "python": details["python"],
                              "codex": details["codex"], "relocation": True,
                              "start_reuse_stop_restart": True, "official_login_url": True,
                              "demo": True, "signature_unchanged": True,
                              "real_login": False, "model_inference": False}, indent=2))
        finally:
            command("stop")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app", type=Path)
    args = parser.parse_args()
    check(args.app.resolve())
