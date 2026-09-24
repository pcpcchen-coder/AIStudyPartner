"""Entry point executed only by the Python runtime inside the distribution."""

import json
import os
import subprocess
import sys
from pathlib import Path

RESOURCES = Path(__file__).resolve().parent
SOURCE = RESOURCES / "app"
sys.path[:0] = [str(SOURCE), str(RESOURCES / "packages")]
os.environ["STUDY_BUNDLE_BOOTSTRAP"] = str(Path(__file__).resolve())
os.environ["STUDY_CODEX_BIN"] = str(RESOURCES / "codex/bin/codex")
os.environ.setdefault("STUDY_RUNTIME_DIR", str(Path.home() / "Library/Application Support/AIStudyPartner"))
os.environ["STUDY_MODEL"] = "gpt-6-astra"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "start"
    if action == "selfcheck":
        import fastapi
        import PIL
        import uvicorn

        print(json.dumps({
            "python": sys.version.split()[0], "fastapi": fastapi.__version__,
            "pillow": PIL.__version__, "uvicorn": uvicorn.__version__,
            "codex": subprocess.check_output([os.environ["STUDY_CODEX_BIN"], "--version"], text=True).strip(),
            "runtime": os.environ["STUDY_RUNTIME_DIR"], "model": os.environ["STUDY_MODEL"],
            "source": str(SOURCE), "executable": sys.executable,
        }))
    elif action == "serve":
        import argparse

        import uvicorn

        parser = argparse.ArgumentParser()
        parser.add_argument("serve")
        parser.add_argument("--port", type=int, default=8765)
        args = parser.parse_args()
        uvicorn.run("study_partner.app:app", host="127.0.0.1", port=args.port,
                    access_log=False, timeout_graceful_shutdown=10)
    else:
        from study_partner.desktop import main as desktop_main

        desktop_main()


if __name__ == "__main__":
    main()
