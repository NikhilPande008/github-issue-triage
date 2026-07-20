# GitHub Issue Triage

An evidence-first system for turning a GitHub issue into a bounded, Docker-isolated reproduction attempt. It fetches and normalizes an issue, extracts a typed reproduction specification with OpenAI, asks Codex to create the smallest useful test change, runs pytest, and persists the resulting evidence for review.

The project is deliberately conservative: a model cannot declare an issue reproduced. A deterministic validator must find both a changed executable pytest test and an assertion failure attributable to that test before the outcome can be `REPRODUCED`.

## What a judge can evaluate

- A typed FastAPI and SQLite/Alembic backend with a read-only React dashboard.
- GitHub REST ingestion separated from internal domain models.
- Strictly validated GPT-5.6 Luna extraction, including retry-on-validation-failure and usage tracking.
- A three-attempt Codex investigation loop with hypotheses, revision reasons, terminal logs, diffs, and pytest output.
- Fresh clone + fresh non-privileged Docker container for every investigation, with cleanup on completion.
- An evidence validator that prevents incidental command, collection, timeout, and unrelated-test failures from being reported as reproductions.
- Evidence-only classification: the classifier does not receive the issue text, extraction, Codex narrative, or hypothesis.
- APIs and dashboard views for the investigation list, summary, attempt timeline, validation result, classification, model usage, and every stored artifact.

## End-to-end flow

```text
GitHub issue
  -> normalized typed issue
  -> validated extraction specification (GPT-5.6 Luna)
  -> up to 3 Docker-isolated Codex + pytest attempts
  -> diff + pytest evidence validator
  -> deterministic reproduction or evidence-only classification
  -> SQLite artifacts and read-only dashboard
```

## Verified production-style run

The configured database includes a rerun of [psf/requests #7564](https://github.com/psf/requests/issues/7564), which requests `FileNotFoundError` for missing TLS material.

Investigation `1c3191cf-93b8-4482-942b-2055fd7cb0f9` demonstrates the complete Docker fallback path:

- Codex’s normal nested Bubblewrap sandbox was unavailable, so the runner used its narrow no-inner-sandbox fallback inside the already isolated Docker container.
- Codex changed `tests/test_requests.py` to require `FileNotFoundError`, `errno.ENOENT`, and the missing filename.
- Attempts 1 and 3 captured the expected failure: `1 failed, 338 passed, 1 skipped, 1 xfailed`.
- The validator currently persists this run as `assertsFailure=false` / `WONT_REPRO` because its pytest-summary parser missed that output. This is an explicit known limitation, not a model-reported success.

The prior negative run and this rerun, including extraction JSON, terminal logs, diffs, and pytest output, are available in `artifacts/` and through the dashboard API.

## Quick start

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker, Node.js/npm (for the dashboard), a Codex authentication file, and an OpenAI API key for extraction and classification. A GitHub token is optional but avoids unauthenticated API limits.

```bash
uv sync
alembic upgrade head

# Optional configuration; defaults use psf/requests and sqlite:///triage.db.
export OPENAI_API_KEY="..."
export GITHUB_TOKEN="..."

# Start the evidence API.
uv run uvicorn triage.api.main:app --reload
```

In another terminal, start the dashboard:

```bash
cd dashboard
npm install
npm run dev
```

Useful commands:

```bash
uv run triage fetch 7564
uv run triage extract 7564
uv run triage investigate 7564
```

`triage investigate` is the only command that performs a real investigation. It needs a running Docker daemon, network access to clone/install dependencies, and Codex authentication at `~/.codex/auth.json` unless `CODEX_AUTH_PATH` is set.

## Review the evidence

With the API running, these endpoints are read-only:

```text
GET /health
GET /investigations
GET /investigations/{id}
GET /investigations/{id}/timeline
GET /investigations/{id}/summary
GET /investigations/{id}/artifacts
```

For the recorded rerun, replace `{id}` with `1c3191cf-93b8-4482-942b-2055fd7cb0f9`.

## Safety and trust boundaries

- Each investigation uses a fresh repository clone and short-lived, non-privileged Docker container; containers do not receive the Docker socket.
- Codex starts in workspace-write mode. Only the exact Bubblewrap user-namespace failure enables the Docker-contained fallback, and both invocations are recorded in the terminal artifact.
- The dashboard has no mutation or execution controls; it only calls GET endpoints.
- Validation requires a changed executable pytest test plus an attributable assertion failure. Classification cannot override an approved reproduction.
- No GitHub issue bodies are persisted. The validated extraction and execution artifacts are persisted so a result can be audited.

## Tests

```bash
uv run pytest
cd dashboard && npm test && npm run build
```

The suite covers GitHub mapping, extraction validation/retry, the investigation loop, Docker runner behavior, Codex fallback selection, validation, classification, persistence, and dashboard APIs/components. The real Docker/Codex fixture smoke test is opt-in because it uses the configured Codex account:

```bash
RUN_DOCKER_CODEX_SMOKE=1 uv run pytest
```

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DEMO_REPOSITORY` | `psf/requests` | GitHub repository to investigate |
| `DATABASE_URL` | `sqlite:///triage.db` | SQLAlchemy database URL |
| `ARTIFACTS_DIR` | `artifacts` | Host directory for copied evidence |
| `INVESTIGATION_RUNNER` | `docker` | `docker` (isolated) or `local` (development only) |
| `SANDBOX_WORKSPACE_DIR` | `sandbox-workspaces` | Temporary clone parent directory |
| `SANDBOX_IMAGE` | `github-issue-triage:latest` | Reused Docker image |
| `CODEX_AUTH_PATH` | `~/.codex/auth.json` | Codex authentication mounted read-only in Docker |
| `PYTEST_TIMEOUT_SECONDS` | `300` | Per-pytest timeout |
| `INVESTIGATION_TIMEOUT_SECONDS` | `900` | Overall Docker investigation timeout |

See [HANDOFF.md](HANDOFF.md) for the current project state and [DECISIONS.md](DECISIONS.md) for the rationale behind durable architectural choices.
