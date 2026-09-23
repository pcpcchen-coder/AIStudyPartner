#!/bin/bash
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
cd "$(dirname "$0")/.."
if ! command -v uv >/dev/null 2>&1; then
  printf '找不到 uv，請重新安裝專案執行環境。\n' >&2
  exit 1
fi
if [ -f .env ]; then
  exec uv run --env-file .env --frozen --python 3.12 python -m study_partner.desktop "$@"
fi
exec uv run --frozen --python 3.12 python -m study_partner.desktop "$@"
