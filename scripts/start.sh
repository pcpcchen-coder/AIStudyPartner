#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if ! command -v uv >/dev/null 2>&1; then
  echo '請先安裝 uv：https://docs.astral.sh/uv/getting-started/installation/'
  exit 1
fi
args=()
if [ -f .env ]; then args+=(--env-file .env); fi
printf '開啟 http://127.0.0.1:8765 ，按 Ctrl+C 結束。\n'
exec uv run "${args[@]}" --frozen --python 3.12 uvicorn study_partner.app:app --host 127.0.0.1 --port 8765 --no-access-log
