"""Keep mutable state outside signed application bundles."""

import os
from pathlib import Path


def runtime_directory():
    configured = os.getenv("STUDY_RUNTIME_DIR")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            raise ValueError("STUDY_RUNTIME_DIR must be an absolute path")
        return path
    return Path(__file__).resolve().parents[1] / ".runtime"
