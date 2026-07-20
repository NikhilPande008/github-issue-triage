# Offline judge demo

This committed snapshot contains real persisted evidence from the `psf/requests`
issue #7564 investigation. It requires no GitHub token, OpenAI API key, Codex
authentication, Docker daemon, or rebuild of the application.

```bash
uv sync
uv run python scripts/seed_demo.py --force
uv run uvicorn triage.api.main:app --reload
```

In another terminal:

```bash
cd dashboard
npm install
npm run dev
```

Open <http://localhost:5173>. The dashboard contains the `REPRODUCED` flagship
record, earlier honest negative records, and their extraction, terminal, pytest,
and Git-diff evidence. The snapshot is intentionally read-only; it is not a
substitute for a live investigation.
