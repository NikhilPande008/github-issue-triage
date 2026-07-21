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
- Evidence-only classification for non-confirming outcomes:
  `NEEDS_INFO`, `WONT_REPRO`, and `NOT_A_BUG`. A behavior-gap confirmation is
  not a claim that the issue is a regression, defect, or intended behavior.
- Persisted linked OpenAI cost/tokens/latency, versioned local price book,
  explicit unpriced Codex wall-time accounting, reservations, budgets, and
  queue backpressure.
- Read-only evidence queue/detail UI, artifact rendering, provenance caveats,
  maintainer-reply previews, advisory related-investigation similarity, and
  accessible navigation.
- Signed webhook intake, durable leased jobs, dry run, repository allowlists,
  idempotent comment markers, and human approval gates for any public comment.
- Immutable review packets, append-only pilot assessments, deterministic review
  consensus, authenticated pilot reviewer queue, privacy-bounded telemetry,
  weekly aggregate reports, consent-gated semantic-corpus export, and
  measurement-only automation eligibility reports.
- Provider interfaces for extraction, classification, and investigation agent;
  Codex is default and Claude Code is an explicitly configured alternative.
  The provider-comparison command makes a consented plan only; it does not run
  or declare a winner.

## Evidence already demonstrated

- Offline demo seed: five selectively exported investigations and 58 referenced
  artifacts across `psf/requests`, `openai/openai-agents-python`, and
  `openai/openai-guardrails-python`. It includes #7564 as flagship, two
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

- Codex requires provider connectivity in its separate agent container. Focused
  tests and confirmations run in a separate no-auth container and are network
  isolated by default. Allowing test network access remains an explicit trust
  decision and is recorded in the reproducibility manifest; this reduces test
  exposure but does not eliminate agent-runtime credential risk.
- Run `triage preflight --repository owner/repository` before a live single or
  batch run. It is read-only, explains separate agent/test boundaries, and
  checks dependency-group ambiguity before extraction, persistence, Docker
  creation, or agent retries. It does not replace actual sandbox setup.
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
