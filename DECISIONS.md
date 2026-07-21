# Architecture Decisions

## ADR-001

Status: Accepted

Date: 2026-07-16

Decision: Use Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, SQLite, uv, and pytest for the production foundation.

Context: The project needs a typed Python service foundation with an HTTP health surface, relational persistence, schema migration, and automated tests.

Alternatives Considered: Other Python web frameworks, non-relational storage, and alternative dependency or test tooling.

Why This Was Chosen: This is the selected production technology stack.

Tradeoffs: SQLite is local-process storage and does not provide a multi-user database deployment model.

Consequences: The project has SQLAlchemy mappings, an Alembic migration history, a FastAPI application, and pytest-based tests.

## ADR-002

Status: Accepted

Date: 2026-07-16

Decision: Normalize GitHub REST payloads into internal typed issue models at the GitHub boundary.

Context: Downstream components require issue information without depending on GitHub response shapes.

Alternatives Considered: Passing raw GitHub payloads to downstream components; mapping payloads inside downstream components.

Why This Was Chosen: The client, mapper, and service have separate responsibilities and downstream code receives a stable internal contract.

Tradeoffs: Mapping must be maintained when required GitHub fields change.

Consequences: `triage.github.client` handles HTTP, `triage.github.mapper` handles normalization, and `triage.github.service` returns `GitHubIssue` models.

## ADR-003

Status: Accepted

Date: 2026-07-16

Decision: Use GPT-5.6 Luna with strict JSON-schema output and Pydantic validation for issue extraction.

Context: Extraction output is consumed as a reproduction specification and must not be silently repaired when it is malformed or contains unagreed fields.

Alternatives Considered: Free-form text parsing; accepting and normalizing partial model output; using a different model tier.

Why This Was Chosen: GPT-5.6 Luna is the selected extraction model, and strict schema output with a second validation boundary preserves the agreed contract.

Tradeoffs: Model output that does not satisfy the schema causes a second API call and can still fail explicitly.

Consequences: Extraction uses the versioned prompt files, retries once only after validation failure, and raises an extraction failure after a second invalid response.

## ADR-004

Status: Accepted

Date: 2026-07-16

Decision: Allow `llm_calls` records without an investigation reference.

Context: `triage extract` records model usage before any investigation workflow or investigation record exists.

Alternatives Considered: Creating an investigation record for extraction; using a synthetic investigation ID; not recording standalone extraction calls.

Why This Was Chosen: It records required model usage without persisting issues or introducing investigation workflow behavior.

Tradeoffs: Consumers of `llm_calls` must handle a missing investigation reference.

Consequences: `investigation_id` is nullable for `llm_calls`, and standalone extraction records include token counts, cost, and latency.

## ADR-005

Status: Accepted

Date: 2026-07-17

Decision: Keep investigation orchestration independent of command execution by using a runner boundary, with a local runner as the current implementation.

Context: The investigation workflow needs to be validated before container isolation is introduced, while preserving a path to Docker-backed execution.

Alternatives Considered: Embedding subprocess calls in the investigation engine; waiting to implement the loop until Docker support exists.

Why This Was Chosen: It permits local workflow validation and lets a future runner replace local execution without changing the bounded investigation loop.

Tradeoffs: Local execution can modify the configured repository and relies on the host's Codex and pytest environment.

Consequences: The engine requests attempt execution through a runner interface; `LocalInvestigationRunner` invokes Codex, pytest, and git diff and writes attempt artifacts.

## ADR-006

Status: Accepted

Date: 2026-07-17

Decision: Use one fresh Docker container and one fresh cloned workspace for each investigation run, while reusing the immutable base image.

Context: Investigations must begin from reproducible repository state without leaking filesystem changes from prior runs.

Alternatives Considered: Reusing a long-lived container; reusing a checked-out workspace; rebuilding the image for every attempt.

Why This Was Chosen: A fresh workspace and container isolate repository state, while image reuse avoids repeating dependency tooling installation at image-build time.

Tradeoffs: Each investigation requires repository cloning and dependency installation; Docker daemon, network access, and cleanup handling are required.

Consequences: The Docker runner owns a sandbox for the full bounded attempt loop, copies attempt artifacts to the host, and removes the container and workspace when its context closes.

## ADR-007

Status: Accepted

Date: 2026-07-17

Decision: Require evidence validation before an investigation can be marked as behavior-gap confirmed.

Context: Codex and pytest exit codes can produce failures unrelated to the reported issue, including syntax, import, collection, timeout, and pre-existing-test failures.

Alternatives Considered: Letting Codex declare success; treating any nonzero pytest exit code as success; applying classification before evidence validation.

Why This Was Chosen: A dedicated validator can require both an executable test change and an assertion failure originating in that changed test.

Tradeoffs: Valid behavior-gap confirmation depends on the supported pytest terminal-output format and can reject ambiguous output.

Consequences: `triage.validation` is the sole source of `assertsFailure`; the investigation engine persists its result and cannot self-declare a behavior gap. Classification must consume this result after validation.

## ADR-008

Status: Accepted

Date: 2026-07-17

Decision: Restrict investigation classification to a typed execution-evidence contract and make validator-approved behavior-gap confirmation deterministic.

Context: Issue prose, extraction content, hypotheses, Codex reasoning, and terminal narration can bias a model to infer conclusions not supported by execution evidence. The `assertsFailure` validator can determine only whether a focused test demonstrates the reported behavior is absent; it cannot establish regression provenance or product intent.

Alternatives Considered: Passing the full investigation context to the classifier; allowing the classifier to choose any outcome including behavior-gap confirmation; using prompt instructions as the only boundary.

Why This Was Chosen: A narrow dataclass input and a classifier method that accepts only that dataclass prevent issue context from entering the classification boundary. Returning `BEHAVIOR_GAP_CONFIRMED` directly for validator-approved evidence prevents an LLM from overriding the deterministic guardrail.

Tradeoffs: The classifier has less context and classification LLM records are standalone because the classification method does not accept an investigation identifier.

Consequences: Classification uses only validator result, pytest exit code/output, and git diff. False validator outcomes may be classified as `NEEDS_INFO`, `WONT_REPRO`, or `NOT_A_BUG`; `BEHAVIOR_GAP_CONFIRMED` is deterministic.

## ADR-009

Status: Accepted

Date: 2026-07-17

Decision: Do not emit `DUPLICATE` without explicit duplicate evidence.

Context: The current pipeline has no semantic duplicate-detection data source.

Alternatives Considered: Letting the classification model infer duplicates from execution evidence; adding duplicate inference to the prompt; adding duplicate detection in this milestone.

Why This Was Chosen: Execution evidence alone cannot substantiate a duplicate finding, and duplicate detection is outside this task's scope.

Tradeoffs: Some investigations that might eventually be identified as duplicates receive another evidence-based non-duplicate classification until duplicate evidence exists.

Consequences: The classifier rejects `DUPLICATE` model output and retries once; semantic duplicate detection remains unimplemented.

## ADR-010

Status: Accepted

Date: 2026-07-17

Decision: Make the investigation dashboard evidence-first and read-only.

Context: Judges need to inspect why an investigation reached its result without a presentation layer being able to mutate investigations, repositories, or evidence.

Alternatives Considered: Adding investigation controls to the dashboard; allowing the frontend direct SQLite access; showing only a final outcome without artifacts.

Why This Was Chosen: Read-only REST APIs keep business logic in backend services and make persisted execution evidence the primary interface for trust.

Tradeoffs: The dashboard can only display data the pipeline persisted and cannot repair or rerun incomplete investigations.

Consequences: The frontend performs only GET requests. It displays missing or deleted artifacts as unavailable and has no retry, edit, execution, or repository-control action.

## ADR-011

Status: Accepted

Date: 2026-07-17

Decision: Persist the validated extraction JSON as an immutable investigation artifact.

Context: The evidence viewer must display the reproduction specification that informed an investigation while remaining a read-only presentation layer.

Alternatives Considered: Re-running extraction when viewing an investigation; showing extraction only from transient CLI output; omitting extraction from evidence.

Why This Was Chosen: Persisting the generated specification once makes the dashboard inspectable without an LLM call and preserves the evidence available at investigation time.

Tradeoffs: Investigations created before this decision do not have an extraction artifact, and artifact storage grows with each investigation.

Consequences: New investigation runs write `extraction.json` under their artifact run directory and record it in the existing artifacts table. Existing missing artifacts remain visible as unavailable rather than being reconstructed.

## ADR-012

Status: Accepted

Date: 2026-07-20

Decision: Use OpenAI JSON-object response mode for issue extraction while retaining strict local Pydantic validation.

Context: The OpenAI strict JSON-schema format rejected the agreed `IssueExtraction` contract because `environment` is a free-form string map, which is incompatible with the provider's strict object-schema subset.

Alternatives Considered: Change `environment` to a fixed set of fields; silently drop environment details; abandon the agreed extraction contract.

Why This Was Chosen: JSON-object mode permits explicitly supplied environment keys without changing the external contract. Pydantic still rejects missing, extra, malformed, and invalid values, and extraction retains its one-retry failure behavior.

Tradeoffs: The provider does not constrain output keys at generation time, so invalid output can require a retry and ultimately fail validation.

Consequences: The extraction prompt explicitly names all nine required keys, and `IssueExtraction` remains the authoritative validation boundary.

## ADR-013

Status: Accepted

Date: 2026-07-20

Decision: Retain Codex's workspace-write sandbox as the preferred Docker invocation and use Codex's no-inner-sandbox mode only after detecting Bubblewrap user-namespace denial, with the Docker container as the enforced isolation boundary.

Context: The real Docker investigation showed that Codex's nested Bubblewrap sandbox could not create a non-privileged user namespace. Its process returned successfully while every repository command and patch failed, preventing evidence generation despite a healthy Docker container.

Alternatives Considered: Enable host user namespaces; run privileged containers; disable Docker isolation; use broad host mounts or the Docker socket; permanently use Codex without its inner sandbox.

Why This Was Chosen: The fallback is limited to the documented Bubblewrap failure, preserves the normal Codex mode where available, and keeps all investigation code inside a fresh container with only the writable repository bind mount and read-only Codex authentication mount.

Tradeoffs: In environments without nested user namespaces, Codex relies on the outer Docker boundary rather than its own filesystem sandbox. The fallback is therefore appropriate only because the container is already isolated and short-lived.

Consequences: The runner records both Codex invocations when fallback occurs, including command, output, exit code, and elapsed time. Docker containers remain non-privileged, receive no Docker socket, and do not set a Docker user-namespace override. If the fallback also reports the namespace failure, the attempt records a clear sandbox error instead of claiming a reproduction.

## ADR-014

Status: Accepted

Date: 2026-07-20

Decision: Attribute only linked, tracked OpenAI API calls to an investigation’s cost and latency; explicitly exclude Codex billing when exact billing data is unavailable.

Context: A global or zero-valued LLM total would misrepresent the operational cost of an individual investigation. Extraction occurs before evidence execution, and retries must also be attributed without leaking usage between investigations.

Alternatives Considered: Allocate global usage proportionally; include zero-cost Codex records in totals; estimate Codex spend; backfill legacy records from averages.

Why This Was Chosen: An investigation is now created before extraction. Linked extraction and classification calls persist provider, price-book version, token usage, latency, and local cost calculation. Unknown pricing and legacy/unlinked calls remain unavailable rather than fabricated.

Tradeoffs: The displayed OpenAI API cost uses a versioned local price book rather than an invoice line item. Codex elapsed execution remains useful operational evidence but is not presented as billable LLM cost or tracked API latency.

Consequences: Queue and detail views label the metrics as tracked LLM API values and explain the Codex exclusion. `triage extract` remains standalone and unlinked. New migrations are additive and historical investigations retain unavailable metrics.
