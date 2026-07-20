# Project Handoff

## Last Updated

2026-07-20 (refreshed)

## Current Milestone

Judge-ready evidence demo and read-only maintainer workflow.

## Completed Tasks

- Production bootstrap: FastAPI health endpoint, typed configuration and domain contracts, SQLAlchemy persistence, Alembic migration, structured logging, and test infrastructure.
- GitHub issue ingestion: authenticated optional-token GitHub REST client, payload normalization, service layer, and `triage fetch <issue-number>` command.
- GPT issue extraction: GPT-5.6 Luna extraction client, versioned prompts, strict schema validation, one validation retry, and LLM usage instrumentation.
- Local investigation engine: bounded three-attempt Codex loop, local pytest execution, per-attempt evidence artifacts, persisted hypotheses and revision reasons, and `triage investigate-local <issue-number>`.
- Docker sandbox runtime: fresh cloned workspace and one container per investigation, dependency installation, in-container Codex/pytest execution, copied artifacts, timeout handling, and mandatory cleanup.
- Evidence validation: strict `assertsFailure` gate that evaluates pytest output and git diff before an investigation can complete successfully.
- Evidence-based classification: an evidence-only GPT-5.6 Luna classifier that runs after validation, records usage metrics, persists its outcome, and cannot override validator-approved reproduction.
- Read-only dashboard: FastAPI investigation/evidence APIs and a React/Vite viewer for persisted investigation summaries, attempt timelines, artifacts, validation, classification, and recorded usage metrics.
- Real demo validation: reran [psf/requests issue #7564](https://github.com/psf/requests/issues/7564), “raise FileNotFoundError for missing TLS material.” Investigation `c5445cae-4f0d-485f-81e8-0c2c22b80060` used the Docker-isolated Codex fallback, changed `tests/test_requests.py` to expect `FileNotFoundError`, and produced the expected focused test failure. The repaired validator persisted `assertsFailure=true` and the deterministic `REPRODUCED` classification.
- Docker-compatible Codex execution: the Docker runner now attempts Codex's normal workspace-write mode first, detects Bubblewrap user-namespace denial from its captured output, and then uses Codex's no-inner-sandbox mode only within the existing isolated Docker container. It records the exact Codex commands, exit codes, elapsed times, and fallback use in the terminal artifact. Pytest runs changed test files when the working-tree status identifies them, otherwise it runs the full suite.
- Pytest evidence validation: the parser now accepts completed plain pytest summaries such as `1 failed, 338 passed, 1 skipped, 1 xfailed`, attributes `FAILED` node IDs even when the test raised a non-`AssertionError` exception, and retains rejection of syntax, import/collection, timeout, crash, and no-test runs. The recorded #7564 artifact now validates as `assertsFailure=true` for `tests/test_requests.py`.
- Prompt evidence handoff: prior terminal output passed to later Codex attempts and pytest output passed to classification are capped at 12,000 characters. The final tail, including failure traces and pytest summary, is preserved with an explicit truncation marker.
- Batch triage: `triage batch-triage` selects newest open non-PR issues sequentially, skips previously completed/failed repository issues by default, and records a resumable per-issue summary.
- Dashboard queue: the default view is a keyboard-accessible maintainer queue with evidence drill-down, browser history support, honest unavailable metrics, and formatted artifacts.
- Maintainer reply preview: `NEEDS_INFO` detail views derive a copyable, preview-only reply from persisted extraction `missing_info`; the dashboard has no GitHub write capability.
- Per-investigation tracked LLM metrics: new investigations are created before extraction so extraction and classification retries are linked. The dashboard shows only linked OpenAI API cost/latency; Codex billing is explicitly excluded. Legacy records remain unavailable.
- Offline judge demo: `scripts/seed_demo.py` installs the committed database/artifact snapshot without API credentials.

## In Progress

None.

## Not Started


## Current Architecture

- `triage.api` exposes the FastAPI application and health endpoint.
- `triage.config` loads typed environment configuration.
- `triage.domain` contains shared typed contracts.
- `triage.github` separates REST communication, mapping, and retrieval orchestration.
- `triage.extraction` separates OpenAI communication, prompt loading, response validation, and retry/instrumentation orchestration.
- `triage.investigation` separates loop orchestration, versioned Codex prompts, runner invocation, and attempt-state contracts.
- `triage.sandbox` separates workspace cloning, Docker image management, container execution, artifact copying, and cleanup.
- `triage.validation` separates git diff analysis, pytest result parsing, and reproduction approval from investigation orchestration.
- `triage.classification` separates the evidence-only classification contract, prompt loading, OpenAI communication, and retry/instrumentation orchestration.
- `triage.api.routes` exposes read-only investigation, timeline, summary, and artifact views from persisted data.
- `dashboard` is a React/Vite presentation layer that consumes the read-only REST APIs only.
- `triage.persistence` contains SQLAlchemy mapped tables and CRUD repositories.
- `migrations` contains the Alembic schema migration.

## Public APIs

- `GET /health` returns `{"status": "ok"}`.
- `GET /investigations` lists persisted investigations with newest-first pagination and optional classification filtering.
- `GET /investigations/{id}`, `/timeline`, `/artifacts`, and `/summary` return read-only investigation detail and evidence views.
- `triage fetch <issue-number>` prints one normalized GitHub issue as JSON.
- `triage extract <issue-number>` fetches an issue and prints a validated reproduction specification as JSON.
- `triage investigate <issue-number>` fetches, extracts, investigates in Docker, validates evidence, persists an evidence-based classification, and prints `assertsFailure`, its validation reason, and the classification.
- `GitHubIssueService.fetch_issue(issue_number)` returns a `GitHubIssue`.
- `GitHubIssueService.fetch_latest_open_issues(limit)` returns normalized open issues.

## Database State

Alembic revision `0006_llm_call_attribution` is current. It adds title persistence and LLM call provider, pricing-version, and attempt provenance to the earlier investigation, validation, and classification schema. Docker investigations persist status, hypotheses, artifact paths, Codex invocation timing, validation, and final classification. New investigations also persist the validated extraction JSON as an immutable artifact. GitHub issue bodies are not persisted.

The real #7564 investigation has one successful completed record, two earlier failed records, and one earlier interrupted record. The successful record (`c5445cae-4f0d-485f-81e8-0c2c22b80060`) contains its extraction JSON plus terminal log, pytest output, and Git diff for the successful first attempt; it records `assertsFailure=true` and `REPRODUCED`. The interrupted record is retained as `FAILED` with an explicit operational-incomplete reason, so it is not presented as an active run.

## Configuration

- `GITHUB_TOKEN` is optional and sent as a bearer token when set.
- `DEMO_REPOSITORY` defaults to `psf/requests`.
- `OPENAI_API_KEY`, `DATABASE_URL`, and `LOG_LEVEL` remain defined for existing/future components.
- Extraction uses only the `gpt-5.6-luna` model.
- `ARTIFACTS_DIR` defaults to `artifacts`.
- `INVESTIGATION_RUNNER` defaults to `docker`; `local` retains the prior runner for development.
- `SANDBOX_WORKSPACE_DIR`, `SANDBOX_IMAGE`, `DEPENDENCY_INSTALL_TIMEOUT_SECONDS`, `PYTEST_TIMEOUT_SECONDS`, `INVESTIGATION_TIMEOUT_SECONDS`, and `CODEX_AUTH_PATH` configure Docker sandbox execution.
- The Docker runner's Codex fallback is automatic only for the exact `bwrap: No permissions to create a new namespace` failure. It does not change Docker privilege, user-namespace, or mount configuration.

## Known Limitations

- GitHub API pagination is not implemented; open-issue retrieval accepts limits from 1 through 100.
- GitHub issue retrieval has no persistence, retry policy, or rate-limit handling.
- Extraction requires a valid OpenAI API key and model access.
- Extraction retries only validation failures; API transport failures are returned to the caller.
- Docker investigation requires a running Docker daemon, network access for cloning/dependency installation, and Codex authentication at `CODEX_AUTH_PATH` when Codex runs in the container.
- An investigation completes successfully only when validation finds a changed executable pytest test and an assertion failure from that changed test. Syntax, import, collection, timeout, crash, internal-error, no-test, and passing outcomes are rejected.
- Classification receives only `asserts_failure`, validation reason, pytest exit code/output, and git diff. It has no issue, extraction, hypothesis, Codex, or terminal-narration inputs.
- `DUPLICATE` is intentionally unavailable because duplicate evidence is not collected. `REPRODUCED` is emitted only by the deterministic validator path.
- Standalone `triage extract` calls remain unlinked by design. Investigation extraction and classification calls are linked to their investigation; legacy records retain unavailable per-investigation metrics.
- Existing investigations from before the dashboard may not have an `extraction_json` artifact; the dashboard displays artifact-unavailable states instead of substituting content.
- Attempt durations and per-attempt pytest exit codes are not persisted separately; the timeline displays them as not recorded when unavailable.
- Pytest validation currently parses standard terminal output rather than JUnit XML.
- The sandbox image is reused, but every workspace and container is fresh and removed after an investigation.
- The first completed #7564 run predates the Docker-compatible Codex fallback. Its three attempts remain valid negative evidence: Codex was blocked by Bubblewrap’s inability to create a user namespace, made no repository change, all Git diffs are empty, and each full pytest run passed (`619 passed, 15 skipped, 1 xfailed`). The validator therefore correctly returned `assertsFailure=false` for that run.
- The successful rerun confirms that the Docker-compatible fallback and repaired validator work together: Codex changed the certificate-file assertion to require `FileNotFoundError` and the missing filename, focused pytest failed as expected, and the persisted investigation is `COMPLETED` with `assertsFailure=true` and `REPRODUCED`.
- The opt-in real Docker/Codex fixture smoke test is skipped by default because it uses the configured Codex account. Set `RUN_DOCKER_CODEX_SMOKE=1` to run it; it uses a temporary repository and removes its container on completion.
- The completed #7564 run used 2,716 Luna input tokens, 614 output tokens, zero cached input tokens, and $0.006400 in standalone extraction/classification records. The current dashboard’s per-investigation cost panel displays $0.000000 because those records are intentionally not linked to an investigation.

## Outstanding Technical Debt

None recorded.

## Next Recommended Task

No outstanding task recorded.

## How to Run

```bash
uv sync
alembic upgrade head
uvicorn triage.api.main:app
cd dashboard && npm install && npm run dev
triage fetch 123
triage extract 123
triage investigate 123
```

## Test Status

79 Python automated tests pass and one opt-in Docker/Codex smoke test is skipped by default. The opt-in smoke was run successfully on 2026-07-20 (`1 passed in 39.74s`): Codex modified a temporary fixture test inside Docker, focused pytest passed, terminal/pytest/diff artifacts were copied, and the container was removed. The test suite covers mocked GitHub, OpenAI, Codex, pytest, Docker, validation evidence, classification responses, dashboard APIs, Codex workspace-write/fallback selection, focused pytest selection, terminal-evidence prompt bounds, and container mount restrictions. Four frontend component/page tests pass; the dashboard production build passes. The configured SQLite database has been migrated through revision `0004_investigation_classification`. A live dashboard walkthrough verified the completed #7564 record through list, detail, timeline, all ten artifacts, validation, classification, and cost panels.
