# EvidenceTrail

Evidence-first, read-only triage for GitHub issues. EvidenceTrail turns a report
into a bounded executable behavior investigation, preserving the extraction, changed
test, pytest output, terminal log, diff, deterministic validation, and final
classification for maintainer review.

License: [MIT](LICENSE). Supported host platforms: macOS or Linux with Python
3.12+, Node.js, and Docker for live investigations. The offline judge demo only
requires Python and Node.js.

## Flagship evidence: `psf/requests` #7564

The committed demo opens directly on real persisted evidence for
[psf/requests #7564](https://github.com/psf/requests/issues/7564), “Raise
`FileNotFoundError` for missing TLS material.” Investigation
`0a379f2f-ee0d-4a60-a7a3-a5682d4e415f` is `COMPLETED`,
`BEHAVIOR_GAP_CONFIRMED`, and `assertsFailure=true`.

Codex changed the existing certificate-path test to require `FileNotFoundError`,
`errno.ENOENT`, and the filename. The focused pytest evidence fails on the
current implementation, which raises `OSError`; the deterministic validator
confirms that the described behavior is absent in the current code. This confirms
a behavior gap, not regression provenance or whether the request is a defect,
feature, documentation change, or intended product behavior. The dashboard exposes the
raw extraction JSON, terminal log, pytest output, and Git diff for inspection.

The committed demo snapshot contains five selectively exported investigations:
Requests #7564; Agents SDK #3563, #3611, and #3654; and Guardrails #70. It
contains three behavior-gap confirmations, one `NEEDS_INFO`, one
`WONT_REPRO`/`COMPLETED_NO_GAP` outcome, and 58 referenced artifacts. The live
database is never copied wholesale when the demo is refreshed.

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

Open <http://localhost:5173>. The public maintainer dashboard is read-only: it
has no issue-comment, label, close, or execution controls. A separate,
authenticated pilot-reviewer surface is available only when pilot review is
explicitly enabled; its append-only assessments and approvals never directly
post to GitHub.

## What Codex accelerated

Codex accelerated the narrow, repetitive investigation work: locating the
relevant TLS certificate branch, proposing a focused executable behavior test,
running focused pytest, and recording each attempt’s terminal output and diff.
It did not decide the verdict. A deterministic validator requires a changed,
executable pytest test plus an attributable assertion failure before the system
may emit `BEHAVIOR_GAP_CONFIRMED`; otherwise the evidence is classified conservatively.

## How it works

```text
GitHub issue (read only)
  -> typed extraction (tracked OpenAI API call)
  -> up to three Docker-isolated Codex + pytest attempts
  -> diff + pytest evidence validator
  -> deterministic behavior-gap confirmation or evidence-only classification
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

Run the read-only preflight first. It performs no investigation, OpenAI call,
Codex invocation, artifact creation, or database write:

```bash
TRIAGE_TEST_NETWORK_POLICY=allowed \
uv run triage preflight --repository psf/requests
```

```bash
uv sync
alembic upgrade head
export OPENAI_API_KEY="..."
export GITHUB_TOKEN="..." # optional, avoids unauthenticated GitHub limits
uv run triage investigate 7564
```

### Network and dependency-setup caveat

`TRIAGE_TEST_NETWORK_POLICY=isolated` is the default for focused tests and
confirmations. Codex runs separately in an agent container with provider
connectivity and its credential mount; the setup and test containers have no
agent credential mount. Test network access requires explicit opt-in with
`TRIAGE_TEST_NETWORK_POLICY=allowed` and is recorded in the reproducibility
manifest.

Some modern Python projects declare test dependencies in a PEP 735
`[dependency-groups]` `dev` group. The sandbox image's `pip` does **not**
support `pip install --group`; provide a repository-specific
`SANDBOX_SETUP_COMMAND` that installs the project and its required test tools.
For example:

```bash
SANDBOX_SETUP_COMMAND='python -m pip install -e . pytest pytest-asyncio pytest-mock pytest-xdist inline-snapshot' \
DEMO_REPOSITORY=openai/openai-agents-python \
uv run triage investigate 3654
```

Use the same explicit command with preflight before starting a run:

```bash
TRIAGE_TEST_NETWORK_POLICY=allowed \
SANDBOX_SETUP_COMMAND='python -m pip install -e . pytest pytest-asyncio pytest-mock pytest-xdist inline-snapshot' \
uv run triage preflight --repository openai/openai-agents-python
```

This command is authoritative: if it fails or times out, the investigation is
recorded as an operational environment-setup failure and is never classified
as a behavior gap.

For sequential, resumable read-only queue processing:

```bash
uv run triage batch-triage --repository psf/requests --count 5
```

Preflight validates known unsafe Codex/network configurations before either
single or batch triage starts; actual sandbox setup still occurs only after a
live investigation is explicitly started.

## Test-runner adapters

The investigation pipeline has a deterministic runner adapter boundary for
repository detection, setup, focused command construction, changed-test
detection, runner-output parsing, and failure validation. The only currently
implemented adapters are **pytest** (the default) and **Vitest**. Jest, Go
`go test`, JUnit-based Java runners, and RSpec are planned adapter interfaces,
not supported execution modes.

Set `TRIAGE_TEST_RUNNER=pytest|vitest|auto`. Explicit selection always wins;
`auto` selects only an unambiguous repository (Python metadata for pytest, or a
`package.json` declaring Vitest). Ambiguous or unsupported projects stop with
an operational setup message and never receive a behavior-gap verdict.

For a Vitest project, do not install Vitest into this application. Declare it
in the target repository's `package.json`; the sandbox uses `npm ci` when a
`package-lock.json` exists, otherwise `npm install`, or the explicitly supplied
`SANDBOX_SETUP_COMMAND`. A focused changed test is run as:

```text
npm exec -- vitest run -- 'tests/changed.spec.ts'
```

Paths are shell-quoted, and only changed JS/TS test paths are included. The
Vitest validator requires a completed named test-file failure and rejects
module/syntax/discovery errors, setup failures, crashes/timeouts, malformed
output, and zero-failure runs. It is therefore the deterministic gate for
`BEHAVIOR_GAP_CONFIRMED`, exactly as pytest remains for Python repositories.

### Structured validation evidence

New pytest and Vitest investigations validate only from a persisted JUnit XML
artifact; terminal output remains visible for maintainers but cannot confirm a
behavior gap by itself. Pytest runs with
`python -m pytest -q --junitxml='/tmp/triage-…-junit.xml'`; Vitest runs with
`npm exec -- vitest run --reporter=junit --outputFile='/tmp/triage-…-junit.xml'`.
The worker copies this file into each attempt as **Structured test results
(JUnit XML)**.

Confirmation requires valid XML, at least one testcase, a focused changed test
with an explicit `<failure>`, and no `<error>` entries. Missing, empty, partial,
or counter-inconsistent XML; all-pass/all-skip results; timeouts/crashes/setup
failures; and mixed `<failure>` plus `<error>` results are inconclusive. Older
persisted artifacts remain viewable unchanged; they are not retroactively
reclassified or supplied with invented structured results.

## Reproducibility and stable confirmation

New sandbox attempts persist a **Reproducibility manifest** containing the
repository and checked-out commit, runner command/version data, image ID and
digest when Docker supplies one, setup command/rationale, resolved `pip freeze`
and Node dependency metadata, lockfile hash, timeouts, separate setup/agent/test
network and credential-mount boundaries, network policy,
confirmation count, timestamps, and integrity hashes for captured artifacts.
This records the environment actually used; it does not claim source dependency
files are pinned.

`TRIAGE_CONFIRMATION_RUNS` defaults to `2`. After a clean initial structured
failure, the exact focused test is run again in the prepared environment without
another Codex edit. Every confirmation must produce a valid focused `<failure>`
and no `<error>`; a pass, error, timeout, malformed result, or disagreement is
recorded as `FLAKY_OR_INCONCLUSIVE`, with `assertsFailure=false`. The classifier
therefore cannot upgrade unstable evidence into `BEHAVIOR_GAP_CONFIRMED`.

`TRIAGE_TEST_NETWORK_POLICY=isolated` is the default. Dependency setup runs in
a temporary network-enabled setup container when needed; test/Codex execution
then uses a separate Docker container with `network_mode=none`. Set `allowed`
explicitly when a test genuinely requires network access; this is recorded in
the manifest. This is Docker-level test isolation, not a claim that dependency
installation was offline.

Use `triage replay path/to/reproducibility_manifest.json` to validate immutable
inputs and create a separate replay plan under `artifacts/replays/`; original
evidence is never overwritten. Replay is best-effort environment reconstruction,
not a byte-for-byte guarantee: unavailable image digests, lock snapshots, or
external dependencies can prevent an exact rerun. Legacy attempts without a
manifest remain readable and are shown as `LEGACY`.

The batch command selects newest open non-pull-request issues, skips completed
or failed issues for that repository unless `--force` is supplied, and persists
the normal extraction → investigation → validation → classification evidence.

## Public and pilot APIs

```text
GET /health
GET /investigations
GET /investigations/{id}
GET /investigations/{id}/timeline
GET /investigations/{id}/summary
GET /investigations/{id}/artifacts
POST /webhooks/github
GET /investigations/webhook-jobs
```

The investigation and evidence endpoints are read-only. Webhook, pilot-session,
assessment, telemetry, report, and approval routes exist behind explicit
configuration and authentication gates; they are not public maintainer controls.

## Opt-in GitHub webhook workflow

The default installation is read-only: webhook ingress is disabled without a
secret and auto-posting is disabled. Local tests and the demo never call
GitHub's write API. Configure a GitHub App as the preferred credential source,
installed only on intended repositories, with **Issues: Read & write** (and no
other permissions needed for this workflow). Use its short-lived installation
token as `GITHUB_TOKEN`; a tightly scoped repository token is also supported.

Create a GitHub App webhook for **Issues** events and point it at
`https://your-host/webhooks/github`. Store its webhook secret and policy only
in deployment configuration:

```bash
export GITHUB_WEBHOOK_SECRET='...'
export WEBHOOK_ALLOWED_REPOSITORIES='owner/repository'
# still safe: workers persist only previews
export GITHUB_AUTO_POST_ENABLED=false
export GITHUB_AUTO_POST_DRY_RUN=true
uv run triage webhook-worker --once
```

For local webhook testing, run the API against a temporary database and send a
locally HMAC-SHA256-signed `issues.opened` fixture; do not point a public GitHub
webhook at a development machine. The endpoint validates the raw request before
parsing JSON, accepts only allowed non-PR `issues.opened` deliveries, and
returns `202` after durable enqueueing. Run the worker separately; it performs
the normal investigation pipeline sequentially.

To enable actual posting for exactly one repository, set all of the following
in the worker environment: `GITHUB_AUTO_POST_ENABLED=true`,
`GITHUB_AUTO_POST_DRY_RUN=false`, and
`GITHUB_AUTO_POST_REPOSITORIES=owner/repository`. Both settings and the
repository allowlist are required. To disable posting immediately, set
`GITHUB_AUTO_POST_ENABLED=false` (or `GITHUB_AUTO_POST_DRY_RUN=true`) and
restart workers. Every decision persists an auditable preview/body, delivery,
investigation, timestamp, outcome, and GitHub comment ID when posted.

Workers use the durable queue controls documented below; public commenting
remains subject to the same opt-in approval gates.

## Durable queue workers

Webhook and batch work share the persisted job queue. New jobs move through
`QUEUED → RUNNING → SUCCEEDED`; transient operational failures move to
`RETRY_SCHEDULED` with exponential backoff, while exhausted retries become
`DEAD_LETTER`. `FAILED` is terminal for non-transient operational failures;
completed deterministic investigations are never retried. Every claim includes
an owner and expiry lease, attempt count, next eligible time, source, priority,
and timing data.

Run one local worker with bounded parallelism:

```bash
export TRIAGE_WORKER_CONCURRENCY=2
export TRIAGE_WORKER_PER_REPOSITORY_CONCURRENCY=1
uv run triage worker --drain
```

Defaults are global concurrency `1`, per-repository concurrency `1`, queue
capacity `100`, a 30-minute lease, and at most `3` attempts. A signed webhook
that arrives when the queue is full receives HTTP 429 so GitHub can retry; it is
never silently discarded. Queue depth, running jobs, attempts, retry/dead-letter
reason, and wait/execution timing are exposed read-only at
`GET /investigations/webhook-jobs`.

SQLite is supported for local single-host use, where conditional claims and
leases prevent ordinary duplicate local execution. It is **not** a supported
multi-host queue backend. For production horizontal workers, deploy against a
shared transactional database such as PostgreSQL and add/use row-locking
(`FOR UPDATE SKIP LOCKED`) in the claim implementation before enabling workers
on more than one host. No external broker is required by this version.

## Budget controls and attributable usage

Tracked OpenAI API cost is separately accounted from Codex execution. Defaults
are `$1.00` per investigation, `$20.00` per repository/day, and `$100.00` per
repository/month, with a conservative `$0.10` reservation before each billable
OpenAI call. Set a budget setting to an explicit empty/unlimited deployment
policy only after operational review; defaults are intentionally bounded.

Reservations are persisted against the investigation, checked against the
repository window, reconciled to the locally priced OpenAI call, and released
when a call fails or costs less than reserved. Unknown-priced models are marked
`UNBUDGETABLE`; the application never invents a USD value. On exhaustion, work
stops with an operational budget reason, no verdict, and no public comment.

Codex has no displayed dollar cost because the application has no attributable
billing source. Instead it records invocation count and wall-clock seconds and
enforces `BUDGET_CODEX_PER_INVESTIGATION_SECONDS=900` by default. Repository
OpenAI windows and Codex resource accounting are visible read-only on an
investigation; SQLite controls are local best-effort, while production hard
concurrent budget guarantees require a shared transactional database.

## Potentially related investigations

Duplicate detection is a separate, advisory similarity layer. It never changes
an investigation classification, never emits `DUPLICATE` as a primary verdict,
and never posts, closes, merges, labels, or otherwise mutates GitHub issues.
It is repository-local by default and produces **Potentially related
investigation** suggestions for maintainer review only.

The canonical similarity document uses persisted structured extraction summary,
expected/actual behavior, missing-information categories, selected runner,
changed test paths, and deterministic validation reason. It deliberately
excludes raw GitHub issue bodies, terminal dumps, stack traces, full code, and
classifier input/output. Exact checksum/structured-field overlap is available
offline. Embeddings are optional and disabled unless a provider/model is
explicitly configured; unavailable or unbudgeted embeddings make semantic
analysis unavailable, not a claim that no duplicates exist.

Similarity scores are evidence-overlap rankings, not duplicate decisions. Use
`GET /investigations/{id}/related` to view the read-only candidates. Current
storage is inspectable persisted rows suitable for small repository-local sets;
a dedicated vector index and human confirmation/dismissal workflow are deferred.

## Immutable semantic-review packets

Completed, classified investigations can receive a versioned **review packet**:
a read-only snapshot of the bounded evidence a design partner needs to assess
whether the generated test represents the reported behavior. Packets are review
snapshots, **not** independent semantic-fidelity verdicts, and never affect
deterministic validation, `BEHAVIOR_GAP_CONFIRMED`, `NEEDS_INFO`, or any other
classification.

Packet schema `1.0` stores canonical JSON and its SHA-256 integrity hash. It
includes the investigation identity/title, persisted structured extraction,
selected runner and manifest command, immutable-at-issuance artifact IDs/paths
and SHA-256 digests for diff/JUnit/manifest evidence, a bounded diff excerpt,
validation and classification state, available model/version metadata, and a
bounded proposed maintainer-comment preview. Raw issue bodies are not currently
persisted and are therefore omitted. Terminal logs, full repository contents,
secrets/authentication material, mutable live GitHub fields, and unbounded
artifact contents are excluded.

The application only inserts packets; it never updates packet content, hash, or
version. A later controlled reissue creates a new version and leaves every
earlier packet unchanged. Historical investigations without a packet remain
readable. `GET /investigations/{id}/review-packets` honestly reports
`AVAILABLE`, `NOT_ISSUED`, or `UNAVAILABLE`; `GET /review-packets/{packet_id}`
returns the bounded stored snapshot. Packet issuance failures are recorded as
operational metadata and do not change an investigation or job outcome.

Reviewer identity, assessments, deterministic consensus, and per-result
approval are available as pilot-only capabilities below. Production SSO/RBAC,
tenant isolation, reviewer assignment, and disagreement resolution remain
deferred.

## Pilot reviewer assessments

Pilot reviewers can append independent semantic-fidelity labels to one specific
immutable review packet. These labels are data collection for evaluating
semantic alignment; they do **not** replace deterministic validation or change
`assertsFailure`, validation reason, classification, job state, artifacts, or
public-comment behavior.

Each assessment answers four required questions with `YES`, `NO`, `UNCERTAIN`,
or `NOT_ENOUGH_CONTEXT`: whether extraction aligns with the issue, the generated
test aligns with the reported behavior, the observed failure supports the
behavior-gap signal, and a proposed public comment is appropriate. Confidence
is `LOW`, `MEDIUM`, or `HIGH`. Reviewers belong to either the `MAINTAINER` or
`INDEPENDENT_ENGINEER` cohort. Their active assessments feed the separate,
deterministic consensus mechanism described below; no model-generated aggregate
or score can override any individual label.

The internal pilot write endpoint is disabled by default. Enable it only with
`PILOT_REVIEW_ENABLED=true` and a deployment-secret reviewer registry such as
`PILOT_REVIEWER_REGISTRY='{"reviewer-a":{"cohort":"MAINTAINER","token":"…"}}'`.
The caller supplies the matching internal reviewer ID and token headers. This
is a narrow configured-registry mechanism for design partners, not SSO or RBAC;
tokens must be stored in deployment configuration and are never persisted or
logged. When disabled, no assessment mutation capability is exposed.

Assessments store the packet ID, hash, and version they reviewed. They are
append-only: updates/deletes are rejected, and a correction creates a new
assessment explicitly referencing the prior active assessment. An immutable
audit row records assessment creation, reviewer ID, packet hash, timestamp, and
a canonical payload hash. Read-only access is available at
`GET /review-packets/{packet_id}/assessments` and
`GET /investigations/{id}/review-assessments`.

The reviewer queue, deterministic consensus, and per-result approval workflow
are implemented for internal pilots. SSO/RBAC, multi-tenant isolation,
reviewer assignment/escalation, disagreement resolution, and production
deployment hardening remain deferred.

## Deterministic semantic-review consensus

The application derives a versioned, deterministic semantic-review state from
the active assessments of exactly one immutable packet. It is separate from
deterministic test validation and the investigation verdict; even
`UNANIMOUSLY_ALIGNED` never authorizes a GitHub comment or other action.

Consensus algorithm `1.0` requires at least one active `MAINTAINER` and two
active `INDEPENDENT_ENGINEER` assessments. Before that threshold, the state is
`PENDING_REVIEW`. At full coverage, all `YES` answers produce
`UNANIMOUSLY_ALIGNED`; any differing answer on any question produces
`DISAGREED`, with the question, values, and assessment IDs retained. Confidence
does not override categorical answers or create a vote.

All four required questions are core alignment questions in version 1.0. A
unanimous `NO` to any produces `REJECTED_ALIGNMENT`; unanimous
`UNCERTAIN`/`NOT_ENOUGH_CONTEXT` answer(s), with no conflicting values, produce
`INSUFFICIENT_CONTEXT`. Missing/inconsistent packet provenance or audit data is
reported as `UNAVAILABLE`. Superseded assessments remain visible but are
excluded from active consensus.

Every active-set change appends a consensus snapshot with packet ID/hash/version,
algorithm version, active assessment IDs and payload hashes, coverage,
structured disagreement, timestamp, and canonical snapshot hash. Snapshots are
immutable and reproducible from their recorded inputs. The current derived
state is returned by `GET /review-packets/{packet_id}` and history by
`GET /review-packets/{packet_id}/consensus-history`.

## Human-approved public comments

Public GitHub comments remain human-approved during pilots. The worker requires
all of: global auto-post enabled, dry-run disabled, repository allowlisted, and
a valid unconsumed per-result `PostingApproval`. Configuration alone can never
post a comment. A failed gate preserves the rendered preview and reports a
review/approval/consensus blocker without changing the investigation or job
result.

An approval is append-only and binds the exact investigation, packet ID/hash/
version, current consensus snapshot/hash/algorithm, normalized rendered-body
SHA-256, classification/comment type, policy version, reviewer identity/cohort/
role, expiry, rationale, and audit hash. Any packet, body, consensus, policy,
eligibility, or expiry change invalidates it during revalidation immediately
before outbound posting. Successful or duplicate-detected posting appends a
`CONSUMED` audit event and records the approval ID/hash on the job; failed posts
do not consume an approval.

`BEHAVIOR_GAP_CONFIRMED` requires an `UNANIMOUSLY_ALIGNED` current consensus and
a maintainer or configured `posting_approver` reviewer. `NEEDS_INFO` requires a
human approval of the exact preview but does not require consensus in policy
version 1.0. All other classifications and operational/flaky outcomes remain
forbidden. Pilot approval creation is available only when the existing pilot
registry mode is enabled, via `POST /investigations/{id}/posting-approvals`;
eligibility and immutable approval history are read-only endpoints. This is not
SSO/RBAC, does not resolve disagreement, and does not set future
corpus/posting policy. The authenticated internal reviewer UI can create only
append-only assessments and approvals; it has no direct GitHub posting action.

## Internal pilot reviewer workflow

The public maintainer inbox remains read-only. Design partners can instead open
`/?reviewer=1` for the separate internal pilot reviewer queue. It shows only
packets needing attention—pending, disagreed, or insufficient semantic review,
and comment previews blocked on review/approval—ordered by review priority and
then oldest review age. The queue includes verdict, `assertsFailure`, cohort
coverage, comment state, cost, and Codex wall time without exposing reviewer
tokens.

Pilot login exchanges a configured registry reviewer ID/token at
`POST /pilot-review/login` for a short-lived HttpOnly, SameSite cookie. The raw
registry token is never returned, stored in browser storage, placed in URLs, or
included in API data. Mutations made using the cookie require the server-issued
CSRF token; logout deletes the server-side session. The cookie is secure by
default (`PILOT_SESSION_SECURE_COOKIE=true`); local HTTP pilots must explicitly
set it false only in their isolated environment. Disabled pilot mode exposes no
working login, queue, or mutation capability.

This in-memory configured-registry session mechanism is intentionally limited
to a local/internal design-partner pilot. It is not production SSO/RBAC, has no
multi-tenant isolation, reviewer assignment/escalation, corpus analytics, or
production deployment hardening. Reviewer actions create only append-only
assessments or posting approvals; the browser has no GitHub posting action.

## Privacy-bounded pilot telemetry

Pilot telemetry measures meaningful reviewer milestones only: explicit review
start/resume/complete, sparse authenticated heartbeats, assessment and approval
milestones, and the already-recorded operational inputs (tracked OpenAI cost,
unpriced Codex invocation/wall time, and attempts). It never records keystrokes,
mouse activity, browser history, full URLs, screen contents, raw issue bodies,
reviewer credentials, session secrets, or unbounded rationale text.

Active review time is estimated from explicit work sessions and sparse
heartbeats. Each inactivity gap is capped by
`PILOT_REVIEW_IDLE_TIMEOUT_SECONDS` (default 900 seconds), so an open tab does
not accumulate indefinite time. Sessions remain per reviewer and packet.
`PILOT_TELEMETRY_RETENTION_DAYS` (default 90) controls safe telemetry-only
purging; packets, assessments, approvals, and evidence are never deleted by
that process.

Authenticated pilot metrics endpoints expose only repository-scoped and
investigation-scoped measured inputs and review durations. These are pilot
instrumentation, not proof of customer value: Codex dollar cost, infrastructure
cost, labor pricing, external user outcomes, and complete latency accounting
remain unavailable. The authenticated pilot Weekly Report page provides
repository-scoped aggregate snapshots; production analytics remain deferred.

## Weekly pilot reports

`triage pilot-weekly-report --repository owner/repo --week-start YYYY-MM-DD`
creates an immutable aggregate-only UTC weekly snapshot using `[week_start,
week_start + 7 days)` boundaries. Authenticated, repository-scoped pilot APIs
also provide JSON and CSV reports. Reports measure investigation/review funnels,
semantic-review states, optional reason-tag distributions, idle-capped estimated
review time, tracked OpenAI cost, and unpriced Codex wall time. They deliberately
exclude reviewer tokens, session hashes, raw activity, issue bodies, and raw
rationales. These are pilot-learning reports, not ROI, retention, accuracy,
fully loaded COGS, or proof of customer value.

## Permissioned semantic-fidelity corpus

`triage export-semantic-corpus --repository owner/repo --output path --operator ref --confirm-evaluation-only`
creates a canonical JSONL evaluation corpus only when every requested repository
has active `EVALUATION_ONLY` consent. Each immutable export records consent
version/audit hash, source packet hashes, cutoff, manifest hash, exclusions, and
dataset-card limitations. Revoking consent blocks future exports immediately and
prior manifests identify their repository provenance; existing external files
are not automatically erased.

Examples contain bounded packet evidence, runner/version metadata, categorical
assessment labels/reason tags, supersession, consensus history, and bounded
posting outcome. They exclude raw issue bodies, terminal logs, raw rationales,
reviewer/session identity, tokens, full repository contents, and mutable GitHub
state. Inclusion is evaluation-only: it does not authorize training, automatic
posting, identity inference, or unattended public-comment policy.

## Automation measurement eligibility

`triage evaluate-automation-eligibility --policy POLICY_ID --operator ref
--confirm-measurement-only` creates an immutable, read-only measurement report.
Policy version 1.0 requires 300 independently adjudicated examples with one
maintainer and two independent-engineer assessments each, zero material
false-alignment signals, no included disagreement, and a one-sided 95% Wilson
lower precision bound of at least 99%. Pending reviews are prominent but outside
the precision denominator; disagreement, rejection, uncertainty, and reviewer
`NO` answers remain blocking evidence.

`MEASUREMENT_ELIGIBLE` means only that this cohort met a measurement threshold
for future human governance discussion. It never enables auto-posting, removes
per-result approval, guarantees a behavior gap, proves customer value, or makes
a production safety claim. Material model, prompt, runner, consent, or policy
changes require a new policy/report evaluation.

## Provider-neutral boundaries

Extraction, evidence classification, and investigation-agent execution have
explicit typed provider contracts with capabilities, normalized usage/provenance,
structured-output requirements, and bounded failure categories. Current default
adapters remain OpenAI for extraction/classification and Codex for sandboxed
investigation. Their existing schemas, budget path, attributable OpenAI pricing,
and unpriced Codex wall-time treatment are unchanged.

Set `EXTRACTION_PROVIDER=openai`, `CLASSIFICATION_PROVIDER=openai`, and
`INVESTIGATION_AGENT_PROVIDER=codex`; unsupported values fail clearly and never
silently fall back. Credentials are configuration-only and are not serialized to
artifacts, APIs, reports, or review packets. A Claude Code adapter is available,
but no live cross-provider comparison or semantic-fidelity result has been
claimed; that still requires consented packets, bounded live runs, and
independent human assessment.

## Claude Code investigation adapter

Set `INVESTIGATION_AGENT_PROVIDER=claude_code`, `CLAUDE_CODE_COMMAND`, and
optionally `CLAUDE_CODE_MODEL` to select the Claude Code CLI adapter. It never
falls back to Codex. Claude Code currently requires
`TRIAGE_TEST_NETWORK_POLICY=allowed` because its configured credential surface
needs provider connectivity; focused test execution remains subject to the
configured sandbox policy. Claude execution is recorded as unpriced agent wall
time unless an attributable supported billing source is added.

`triage compare-investigation-providers --repository owner/repo --baseline codex
--candidate claude_code --max-examples N --max-wall-seconds S --operator ref
--output path --confirm-evaluation-only` creates a consented bounded comparison
plan only. It does not run agents, use live credentials, or claim a winner.
Mechanical completion/validation metrics must remain separate from independent
human semantic review. A live smoke run or comparison requires explicit operator
approval with selected consented packets, runtime/budget cap, credentials, and
network policy supplied beforehand.

## Verification

```bash
python3 -m pytest -q
cd dashboard && npm test -- --run && npm run build
```

See [HANDOFF.md](HANDOFF.md) for current operational state and
[DECISIONS.md](DECISIONS.md) for durable architectural decisions. See
[PRODUCT_REPORT.md](PRODUCT_REPORT.md) for the review-ready product report,
including live cross-repository evidence and explicit limitations.

## Live cross-repository validation — 2026-07-21

Six approved, read-only live investigations were run sequentially with
repository-specific test setup and the explicitly recorded `allowed` network
policy. No GitHub comments, labels, closures, or other GitHub writes occurred.

| Repository | Issue | Verdict | Deterministic evidence |
| --- | ---: | --- | --- |
| `openai/openai-agents-python` | [#3563](https://github.com/openai/openai-agents-python/issues/3563) | `BEHAVIOR_GAP_CONFIRMED` | New failing assertion in `tests/test_call_model_input_filter.py` |
| `openai/openai-agents-python` | [#3611](https://github.com/openai/openai-agents-python/issues/3611) | `NEEDS_INFO` | No modified executable pytest test |
| `openai/openai-agents-python` | [#3654](https://github.com/openai/openai-agents-python/issues/3654) | `WONT_REPRO` | No modified executable pytest test |
| `openai/openai-guardrails-python` | [#70](https://github.com/openai/openai-guardrails-python/issues/70) | `BEHAVIOR_GAP_CONFIRMED` | New failing assertion in `tests/unit/test_agents.py` |
| `openai/openai-guardrails-python` | [#75](https://github.com/openai/openai-guardrails-python/issues/75) | `NEEDS_INFO` | No modified executable pytest test |
| `openai/openai-guardrails-python` | [#38](https://github.com/openai/openai-guardrails-python/issues/38) | `NEEDS_INFO` | No modified executable pytest test |

Distribution: two behavior-gap confirmations, three `NEEDS_INFO`, one
`WONT_REPRO`, and zero `NOT_A_BUG`. The system declined to confirm 4 of the 6
selected issues, returning bounded non-confirming outcomes instead. The six
selected records used about $0.03 of tracked OpenAI API cost, about 46 seconds
of tracked OpenAI API latency, and about 23 minutes of unpriced Codex
execution. Initial #3654 environment and
network-misconfiguration attempts remain in the audit trail as operational
failures and are excluded from this distribution.
