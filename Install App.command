#!/bin/bash
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
cd "$(dirname "$0")"
if ! command -v uv >/dev/null 2>&1; then
  printf '請先安裝 uv：https://docs.astral.sh/uv/getting-started/installation/\n'
  read -r -p '按 Enter 關閉。'
  exit 1
fi
uv run --frozen --python 3.12 python scripts/build_macos_app.py
open -R "$HOME/Applications/AIStudyPartner.app"
printf '已安裝 AIStudyPartner 伴讀。從應用程式或 Spotlight 開啟；退出 App 會關閉服務。\n'
