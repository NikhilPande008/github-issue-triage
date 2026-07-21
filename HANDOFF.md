# Project Handoff

## Last updated

2026-07-21

## Current state

EvidenceTrail is an evidence-first GitHub issue investigation system. It turns a
read-only GitHub issue payload into a bounded sandboxed investigation and makes
the extraction, changed test, structured JUnit result, terminal output, diff,
reproducibility manifest, deterministic validation, costs, and classification
inspectable in a React/FastAPI dashboard.

The public maintainer dashboard is read-only. A separate, explicitly enabled
internal pilot workflow supports semantic review, per-result human approval,
and tightly gated GitHub posting. Nothing in the default demo or local public
dashboard can write to GitHub.

Database migration head is `0022_completed_no_gap_status`.

## What is implemented

- GitHub issue retrieval, pagination-aware batch selection, rate-limit guidance,
  setup-failure evidence, and sequential/resumable investigation orchestration.
- Fresh Docker workspaces, bounded Codex attempts, pytest and Vitest adapters,
  repository-specific setup commands, JUnit XML validation, confirmation reruns,
  reproducibility manifests, and replay planning.
- Deterministic `BEHAVIOR_GAP_CONFIRMED` validation: a changed focused test must
  have a clean structured `<failure>` and no error, timeout, crash, setup
  failure, malformed report, or flaky confirmation.
- The read-only “Why this failure counts” explainer reconstructs persisted
  deterministic gate checks for detail pages and the Evidence Brief. New JUnit
  evidence is authoritative; legacy records visibly retain their older
  provenance and unavailable checks.
- New live diffs receive a persisted proof-integrity report before validation.
  It rejects only clear manufactured/unrelated proof patterns and records
  ambiguous anchors or mock failures as human-review flags.
- Evidence-only classification for non-confirming outcomes:
  `NEEDS_INFO`, `WONT_REPRO`, and `NOT_A_BUG`. A behavior-gap confirmation is
  not a claim that the issue is a regression, defect, or intended behavior.
- Persisted linked OpenAI cost/tokens/latency, versioned local price book,
  explicit unpriced Codex wall-time accounting, reservations, budgets, and
  queue backpressure.
- Read-only evidence queue/detail UI, artifact rendering, provenance caveats,
  advisory **Maintainer next action** guidance from persisted evidence,
  preview-only maintainer replies, related-investigation similarity, and
  accessible navigation. No public GitHub mutation or retry control exists.
- Signed webhook intake, durable leased jobs, dry run, repository allowlists,
  idempotent comment markers, and human approval gates for any public comment.
- Immutable review packets, append-only pilot assessments, deterministic review
  consensus, authenticated pilot reviewer queue, privacy-bounded telemetry,
  weekly aggregate reports, consent-gated semantic-corpus export, and
  measurement-only automation eligibility reports.
- Public evidence details show only aggregate semantic-fidelity provenance;
  authenticated, repository-scoped reviewers can inspect packet evidence and
  submit append-only assessments. The `ALIGNED`/`UNCLEAR`/`MISALIGNED` display
  is derived from the four existing judgments and never changes classification.
- Provider interfaces for extraction, classification, and investigation agent;
  Codex is default and Claude Code is an explicitly configured alternative.
  The provider-comparison command makes a consented plan only; it does not run
  or declare a winner.

## Evidence already demonstrated

- Offline demo seed: five selectively exported investigations and 68 referenced
  artifacts across `psf/requests`, `openai/openai-agents-python`, and
  `openai/openai-guardrails-python`. It includes the modern #7564 flagship
  confirmation with exact target/JUnit/proof-integrity/confirmation provenance, two
  cross-repository confirmations, `NEEDS_INFO`, and `WONT_REPRO`/
  `COMPLETED_NO_GAP` evidence.
- 2026-07-21 cross-repository live run, read-only and sequential:

  | Repository | Issues | Distribution |
  | --- | --- | --- |
  | `openai/openai-agents-python` | #3563, #3611, #3654 | 1 `BEHAVIOR_GAP_CONFIRMED`, 1 `NEEDS_INFO`, 1 `WONT_REPRO` |
  | `openai/openai-guardrails-python` | #70, #75, #38 | 1 `BEHAVIOR_GAP_CONFIRMED`, 2 `NEEDS_INFO` |

  The two confirmations were anchored in new failing assertions at
  `tests/test_call_model_input_filter.py` and `tests/unit/test_agents.py`.
  The system declined to confirm 4 of the 6 selected issues, returning bounded
  non-confirming outcomes instead. Selected-run totals: about $0.03 tracked
  OpenAI cost, about 46 seconds tracked OpenAI latency, and about 23 minutes of
  explicitly unpriced Codex time.
  No GitHub writes occurred.

## Current operational caveats

- The `/?live=1` controlled live demo is disabled by default. It accepts only
  explicitly allowlisted repositories/issues, enqueues durable `LIVE_DEMO`
  jobs, and never creates a GitHub comment preview or post. Offline evidence
  remains the default judge route; a real run requires explicit operator
  approval after preflight.
- `/?compare=1` is a public, read-only explanation of generic AI triage versus
  the Issue Triage evidence workflow. Its evidence links are selected from
  persisted records and remain unavailable rather than fabricated when absent.
- `/?evaluation=1` reads only the versioned curated retrospective dataset. It
  currently contains three source-backed seeded cases; public issue history is
  categorized as ambiguous or insufficient when it does not establish the
  bounded interpretation.

- Focused test and confirmation execution have no Codex credential mount and
  are network-isolated by default. The agent phase still requires provider
  connectivity. This reduces test-execution exposure but does not claim
  complete protection from all agent-runtime supply-chain or credential risks.
  Setup has dependency-install network access only and no Codex mount;
  manifests record each role and the confirmation boundary.
- Modern structured confirmation additionally requires an AST-derived exact
  changed pytest node and a matching JUnit testcase. File-only or unavailable
  selection remains diagnostic evidence and cannot set `assertsFailure=true`.
- Run `triage preflight --repository owner/repository` before a live single or
  batch run. It is read-only, explains separate agent/test boundaries, and
  performs no GitHub read, extraction, persistence, Docker creation, or agent
  retries. It does not replace actual sandbox setup; setup selection happens
  after the live checkout.
- The sandbox image's pip does not support PEP 735 `pip install --group`. For a
  repository that keeps pytest tools only in `[dependency-groups].dev`, supply
  an explicit `SANDBOX_SETUP_COMMAND`. A failure is persisted as an operational
  failure and receives no verdict.
- Normal non-confirming terminal reviews use `COMPLETED_NO_GAP` with their
  bounded classification. `FAILED` remains reserved for operational failures
  without a valid terminal classification.
- SQLite is local single-host only. Multi-host workers and strict concurrent
  budget guarantees require PostgreSQL-grade transactional claims/locks.
- Semantic fidelity is measured through human review but has no populated,
  independently adjudicated external corpus yet. Automation eligibility is
  measurement only and never removes individual human posting approval.
- Codex and Claude Code dollar cost are unavailable. The system records their
  invocation/wall time but does not invent billing values.
- Supported live test runners are pytest and Vitest. Cargo/Rust, Jest, Go,
  JUnit/Java, and RSpec execution adapters are not implemented.
- Production SSO/RBAC, tenant isolation, production session storage,
  reviewer assignment/escalation, vector indexing, full COGS, and real
  design-partner retention evidence remain deferred.

## Verification baseline

Last full verified test/build baseline:

```text
python3 -m pytest -q            # 175 passed, 1 skipped
cd dashboard && npm test -- --run  # 22 tests across 11 files passed
cd dashboard && npm run build      # passed
```

## Primary references

- [README.md](README.md): installation, architecture, safety controls,
  pilot workflow, and live-run instructions.
- [PRODUCT_REPORT.md](PRODUCT_REPORT.md): review-ready capability and risk
  report.
- [DECISIONS.md](DECISIONS.md): architectural decision records.
- [demo/README.md](demo/README.md): offline demo snapshot.
