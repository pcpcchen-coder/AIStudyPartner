#!/bin/bash
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
cd "$(dirname "$0")"
if [ ! -d "$HOME/Applications/AIStudyPartner.app" ]; then
  uv run --frozen --python 3.12 python scripts/build_macos_app.py
fi
exec open "$HOME/Applications/AIStudyPartner.app"
