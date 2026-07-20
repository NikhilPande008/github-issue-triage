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
record and its extraction, terminal, pytest, and Git-diff evidence. The snapshot
is intentionally read-only; it is not a substitute for a live investigation.

Maintainers refresh this snapshot with `scripts/export_demo.py`, which selects
explicit investigation IDs and copies only their persisted rows and referenced
artifacts into a newly created demo database. It never copies the live
`triage.db` wholesale.
