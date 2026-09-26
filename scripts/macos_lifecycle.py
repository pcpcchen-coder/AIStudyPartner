"""Remove Launch Services registrations owned by temporary build/test folders."""

import contextlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

LSREGISTER = Path('/System/Library/Frameworks/CoreServices.framework/Frameworks/'
                  'LaunchServices.framework/Support/lsregister')


def unregister(path):
    if sys.platform == 'darwin':
        subprocess.run([str(LSREGISTER), '-u', str(path)], capture_output=True, check=False)


def registered_paths():
    if sys.platform != 'darwin':
        return []
    result = subprocess.run([str(LSREGISTER), '-dump'], capture_output=True, text=True, check=True)
    return [Path(match) for match in re.findall(r'^path:\s+(.*?) \(0x[0-9a-f]+\)', result.stdout, re.MULTILINE)]


@contextlib.contextmanager
def temporary_apps(prefix):
    # A noindex directory reduces discovery; explicit cleanup also handles stale
    # registrations left behind by osacompile or by moving a bundle during build.
    with tempfile.TemporaryDirectory(prefix=prefix, suffix='.noindex') as folder:
        root = Path(folder).resolve()
        try:
            yield root
        finally:
            paths = set(root.rglob('*.app'))
            paths.update(path for path in registered_paths() if path.resolve().is_relative_to(root))
            for path in paths:
                unregister(path)
