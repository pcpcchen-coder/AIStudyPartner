#!/bin/sh
set -eu
resources=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
unset PYTHONPATH PYTHONHOME
exec "$resources/python/bin/python3.12" -I -B "$resources/bootstrap.py" "$@"
