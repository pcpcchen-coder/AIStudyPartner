# Project conventions

- This is a macOS webcam study companion, with Traditional Chinese UI and multi-subject teaching.
- Preserve the user's selected authentication: ChatGPT browser OAuth through official Codex app-server. Do not add API-key fallback, scrape web sessions, read auth tokens, or use private token endpoints.
- Keep `.runtime/`, `.env`, credentials, real child images and transcripts out of Git.
- Inspect current behavior before changing it. Preserve explicit cloud opt-in and localhost-only access.
- Never silently downgrade the user-selected model or authorize tools to execute student content.
- Treat demo fixtures, mocked protocol tests, live model inference, physical camera tests and educational acceptance as separate evidence levels.
- Run relevant Python, motion-gate and browser tests. Never use real student data or paid/limited model calls in CI.

- Install/update must replace existing AIStudyPartner apps and unregister old entries, preserving account/study data. Keep reversible ZIP backups, not extra executable apps.
- Distribution outputs must contain DMGs only (plus guides/checksums), never loose .app copies. Build/test app folders must unregister Launch Services entries in finally cleanup, including failures and moved/deleted paths.
