# Issue Triage

Evidence-first, read-only triage for GitHub issues. Issue Triage turns a report
into a bounded reproduction investigation, preserving the extraction, changed
test, pytest output, terminal log, diff, deterministic validation, and final
classification for maintainer review.

License: [MIT](LICENSE). Supported host platforms: macOS or Linux with Python
3.12+, Node.js, and Docker for live investigations. The offline judge demo only
requires Python and Node.js.

## Flagship evidence: `psf/requests` #7564

The committed demo opens directly on real persisted evidence for
[psf/requests #7564](https://github.com/psf/requests/issues/7564), “Raise
`FileNotFoundError` for missing TLS material.” Investigation
`c5445cae-4f0d-485f-81e8-0c2c22b80060` is `COMPLETED`,
`REPRODUCED`, and `assertsFailure=true`.

Codex changed the existing certificate-path test to require `FileNotFoundError`,
`errno.ENOENT`, and the filename. The focused pytest evidence fails on the
current implementation, which raises `OSError`; the deterministic validator
accepts that changed-test failure as a reproduction. The dashboard exposes the
raw extraction JSON, terminal log, pytest output, and Git diff for inspection.

Earlier runs remain in the demo as honest negative evidence. They are not
rewritten into successes.

## Judge demo: no keys, no rebuild

The tracked [demo snapshot](demo/README.md) lets a reviewer inspect the full
evidence trail without GitHub, OpenAI, Codex, Docker, or API credentials:

```bash
uv sync
uv run python scripts/seed_demo.py
uv run uvicorn triage.api.main:app --reload
```

In another terminal:

```bash
cd dashboard
npm install
npm run dev
```

Open <http://localhost:5173>. The dashboard is read-only: it only calls `GET`
endpoints and has no issue-comment, label, close, or execution controls.

## What Codex accelerated

Codex accelerated the narrow, repetitive investigation work: locating the
relevant TLS certificate branch, proposing a minimal regression-test change,
running focused pytest, and recording each attempt’s terminal output and diff.
It did not decide the verdict. A deterministic validator requires a changed,
executable pytest test plus an attributable assertion failure before the system
may emit `REPRODUCED`; otherwise the evidence is classified conservatively.

## How it works

```text
GitHub issue (read only)
  -> typed extraction (tracked OpenAI API call)
  -> up to three Docker-isolated Codex + pytest attempts
  -> diff + pytest evidence validator
  -> deterministic REPRODUCED or evidence-only classification
  -> SQLite + artifacts -> read-only FastAPI + React dashboard
```

- GitHub REST access is read-only.
- Every live investigation uses a fresh clone and a short-lived,
  non-privileged Docker container without the Docker socket.
- Extraction and evidence classification are validated structured OpenAI calls;
  their linked, tracked API cost/latency is shown only when recorded. Codex
  billing is explicitly excluded because exact Codex cost data is unavailable.
- `NEEDS_INFO` detail pages can render a copyable maintainer reply from the
  persisted extraction; it is a preview and is never posted to GitHub.

## Live investigation setup

Live work needs Docker, a Codex authentication file, network access for the
target repository, and an OpenAI API key for extraction/classification.

```bash
uv sync
alembic upgrade head
export OPENAI_API_KEY="..."
export GITHUB_TOKEN="..." # optional, avoids unauthenticated GitHub limits
uv run triage investigate 7564
```

For sequential, resumable read-only queue processing:

```bash
uv run triage batch-triage --repository psf/requests --count 5
```

The batch command selects newest open non-pull-request issues, skips completed
or failed issues for that repository unless `--force` is supplied, and persists
the normal extraction → investigation → validation → classification evidence.

## Read-only APIs

```text
GET /health
GET /investigations
GET /investigations/{id}
GET /investigations/{id}/timeline
GET /investigations/{id}/summary
GET /investigations/{id}/artifacts
```

## Verification

```bash
python3 -m pytest -q
cd dashboard && npm test -- --run && npm run build
```

See [HANDOFF.md](HANDOFF.md) for current operational state and
[DECISIONS.md](DECISIONS.md) for durable architectural decisions.
