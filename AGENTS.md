# Project conventions

- This is a macOS webcam study companion, with Traditional Chinese UI and multi-subject teaching.
- Preserve the user's selected authentication: ChatGPT browser OAuth through official Codex app-server. Do not add API-key fallback, scrape web sessions, read auth tokens, or use private token endpoints.
- Keep `.runtime/`, `.env`, credentials, real child images and transcripts out of Git.
- Inspect current behavior before changing it. Preserve explicit cloud opt-in and localhost-only access.
- Never silently downgrade the user-selected model or authorize tools to execute student content.
- Treat demo fixtures, mocked protocol tests, live model inference, physical camera tests and educational acceptance as separate evidence levels.
- Run relevant Python, motion-gate and browser tests. Never use real student data or paid/limited model calls in CI.
