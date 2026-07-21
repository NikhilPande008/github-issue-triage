# EvidenceTrail — Product Report

**Report date:** 2026-07-21  
**Product state:** functioning local/pilot system; not a production SaaS claim

## 1. Executive summary

EvidenceTrail is an evidence-first system for helping maintainers assess GitHub
issues. It does not treat an LLM's judgment as proof. Instead, it extracts a
bounded behavior specification, asks a sandboxed coding agent to make the
smallest focused test change it can justify, runs that test, and applies a
deterministic validator to the resulting structured test evidence.

The strongest product output is **Behavior gap confirmed**
(`BEHAVIOR_GAP_CONFIRMED`, `assertsFailure=true`). It means that a changed,
focused test for the reported behavior produced a clean, confirmed assertion
failure against the repository's current code. It does **not** claim that the
issue is a regression, a bug, a security vulnerability, or the behavior the
project should ultimately choose.

Every outcome is inspectable: structured extraction, hypotheses, changed test,
JUnit XML, terminal log, diff, validation reason, reproducibility manifest,
classification, and attributable operational metrics are persisted. The public
maintainer interface is deliberately read-only. GitHub comments, when enabled
for a controlled pilot, require multiple independent policy and human-approval
gates.

## 2. The maintainer problem it addresses

Maintainers receive reports that vary widely in precision. A report may be a
real behavior gap, an incomplete feature request, a documentation question, a
duplicate, an environment mismatch, or simply lack enough reproduction detail.
The expensive work is often converting prose into a minimal executable claim
and then determining whether that claim fails cleanly in the current codebase.

EvidenceTrail aims to shorten that evidence-gathering step while keeping the
result reviewable. The intended workflow is:

1. An issue is selected from an explicitly scoped GitHub repository.
2. The system produces a typed extraction of behavior, environment, and missing
   information.
3. A short-lived sandbox attempts a focused test-only reproduction.
4. A deterministic validator decides whether the evidence is mechanically clean.
5. A maintainer opens the evidence trail rather than trusting a black-box label.
6. For `NEEDS_INFO`, the dashboard can provide a copyable, preview-only request
   for the missing details.

## 3. What the product can do today

| Area | Delivered capability | Important boundary |
| --- | --- | --- |
| Issue intake | Read GitHub issues, exclude pull requests, normalize payloads, select newest open issues, paginate candidate pages, skip prior terminal runs, rate-limit guidance | GitHub writes are not part of normal intake |
| Extraction | Typed, validated OpenAI extraction with retry and usage provenance | Extraction is not a verdict |
| Investigation | Up to three focused coding-agent attempts in a fresh Docker workspace | Agent output is evidence to validate, not authority to classify |
| Test runners | Pytest and Vitest adapters with explicit/auto runner selection | Jest, Cargo/Rust, Go, Java/JUnit, and RSpec are not executable adapters |
| Validation | JUnit XML is authoritative; changed focused test plus clean `<failure>` required | Terminal output alone cannot confirm a behavior gap |
| Reliability | Confirmation rerun, manifest, artifact hashes, network-policy recording, replay-plan command | Replay is best-effort, not byte-for-byte reconstruction |
| Outcomes | `BEHAVIOR_GAP_CONFIRMED`, `NEEDS_INFO`, `WONT_REPRO`, `NOT_A_BUG`; no primary `DUPLICATE` | A confirmation is not a semantic bug decision |
| Evidence UI | Queue, details, timeline, structured artifact viewer, diff highlighting, metrics, copy controls, keyboard navigation | Public dashboard does not run, edit, or post anything |
| Queueing | Durable jobs, leases, retry/backoff, per-repository concurrency, queue limit, batch enqueue mode | SQLite is local single-host only |
| Costs | Linked OpenAI tokens, latency, versioned local cost calculation, reservations/budgets; Codex wall time | Codex/Claude dollar cost is intentionally unavailable |
| Related work | Advisory repository-local similarity suggestions | Never relabels an issue as `DUPLICATE` or comments automatically |
| Human review | Immutable packets, independent assessments, deterministic consensus, per-result approvals | Pilot only; no production SSO/RBAC or automation authority |
| GitHub workflow | Signed webhook intake and tightly gated worker comments | Default is disabled/dry-run; per-result approval is always required |
| Evaluation | Privacy-bounded telemetry, weekly reports, consent-gated corpus export, eligibility measurement | No external corpus-based performance claim exists yet |
| Providers | Typed provider interfaces; OpenAI + Codex defaults; explicitly configured Claude Code adapter | No live benchmark or provider winner claimed |

## 4. End-to-end architecture

```text
GitHub issue (read only)
  -> validated typed extraction (OpenAI; linked usage)
  -> fresh Docker workspace + repository-specific setup
  -> bounded Codex/Claude agent attempt to add a focused test
  -> focused pytest or Vitest command emits JUnit XML
  -> deterministic validator + optional confirmation run
  -> evidence-only classification for non-confirming outcomes
  -> SQLite/artifact store
  -> FastAPI + React evidence viewer

Optional pilot path:
  immutable review packet -> independent human assessments -> consensus
  -> exact-preview approval -> separately running allowlisted GitHub worker
```

### 4.1 Deterministic evidence gate

For new pytest and Vitest investigations, terminal text is visible but cannot
produce `assertsFailure=true` by itself. The validator requires all of:

- valid, non-empty JUnit XML;
- at least one executed test case;
- an explicit `<failure>` in a changed, focused test path;
- no `<error>` case;
- no setup failure, timeout, crash, malformed report, or counter inconsistency;
- matching confirmation execution(s), by default two total runs, once an initial
  clean failure is found.

Syntax errors, import/collection failures, test discovery failures, all-pass or
all-skip output, no changed executable test, mixed failure/error reports, and
flaky confirmation results are all rejected as confirmation evidence.

### 4.2 Classification boundary

`BEHAVIOR_GAP_CONFIRMED` comes directly from the deterministic validation path;
an LLM cannot upgrade non-confirming evidence into it. For every other case,
the evidence-only classifier receives constrained validation/diff/test output,
not the raw issue body, extraction, or terminal narrative. This separation
reduces—but does not eliminate—the risk of a plausible-looking generated test
misrepresenting the issue.

### 4.3 Sandbox and reproducibility

Each run gets a fresh repository clone and a short-lived non-privileged Docker
container with no Docker socket. The reproducibility manifest records commit,
runner command/version, image identity when available, selected setup command
and reason, dependency snapshots, lockfile metadata, network policy, timeouts,
confirmation count, timestamps, and artifact hashes.

Dependency setup can use an explicit `SANDBOX_SETUP_COMMAND`, otherwise the
system attempts a supported manifest fallback. A setup command failure is
persisted with terminal, test-output, diff, and manifest evidence as an
operational failure; it cannot silently become a negative product verdict.

## 5. Current outcome semantics

| Outcome | Meaning | What it does not mean |
| --- | --- | --- |
| `BEHAVIOR_GAP_CONFIRMED` | Clean, focused changed test fails against current code and survives confirmation | Confirmed regression, defect, intent, priority, or security impact |
| `NEEDS_INFO` | Available evidence does not support a focused reproduction; extraction identifies missing detail | Issue is invalid or rejected |
| `WONT_REPRO` | The bounded investigation did not produce evidence supporting the claimed behavior gap | Mathematical proof the report can never be reproduced |
| `NOT_A_BUG` | Evidence-only classification identifies an intentional/non-defect framing | A maintainer's final policy decision |
| Operational failure | Setup, budget, runner, timeout, or infrastructure prevented a valid investigation | Any issue disposition |
| `FLAKY_OR_INCONCLUSIVE` | Initial evidence did not reproduce cleanly in confirmation | A behavior-gap confirmation |

Normal non-confirming terminal reviews use `COMPLETED_NO_GAP` with a bounded
classification such as `NEEDS_INFO` or `WONT_REPRO`. `FAILED` is reserved for
an operational failure with no valid terminal classification.

## 6. Evidence and demo record

### 6.1 Flagship real case

The committed demo includes the real `psf/requests` #7564 investigation.
Codex changed a certificate-path test to expect `FileNotFoundError`, `errno`,
and filename evidence. Current code raised `OSError`; focused pytest output
included the genuine summary form:

```text
1 failed, 338 passed, 1 skipped, 1 xfailed
```

The structured-validation path recorded `assertsFailure=true` and
`BEHAVIOR_GAP_CONFIRMED`. This case originally exposed a parser defect: the
older terminal-output parser failed to recognize a failed count alongside
passed/skipped/xfail counts. The parser was repaired and later superseded by
authoritative JUnit validation for new runs.

The committed demo seed contains five selectively exported records across
`psf/requests`, `openai/openai-agents-python`, and
`openai/openai-guardrails-python`: three confirmations, one `NEEDS_INFO`, and
one `WONT_REPRO`/`COMPLETED_NO_GAP` case, with 58 referenced artifacts. It is a
local evidence snapshot, not a live execution environment.

### 6.2 Cross-repository live validation, 2026-07-21

The system was run sequentially, with no GitHub writes, against six selected
issues outside the original Requests repository.

| Repository / issue | Result | Key deterministic evidence | Tracked OpenAI cost (rounded) | Codex wall time |
| --- | --- | --- | ---: | ---: |
| `openai/openai-agents-python` [#3563](https://github.com/openai/openai-agents-python/issues/3563) | `BEHAVIOR_GAP_CONFIRMED` | New failing assertion in `tests/test_call_model_input_filter.py` | $0.004 | 120.423s |
| `openai/openai-agents-python` [#3611](https://github.com/openai/openai-agents-python/issues/3611) | `NEEDS_INFO` | No modified executable pytest test | $0.007 | 260.691s |
| `openai/openai-agents-python` [#3654](https://github.com/openai/openai-agents-python/issues/3654) | `WONT_REPRO` | No modified executable pytest test | $0.003 | 283.849s |
| `openai/openai-guardrails-python` [#70](https://github.com/openai/openai-guardrails-python/issues/70) | `BEHAVIOR_GAP_CONFIRMED` | New failing assertion in `tests/unit/test_agents.py` | $0.007 | 160.510s |
| `openai/openai-guardrails-python` [#75](https://github.com/openai/openai-guardrails-python/issues/75) | `NEEDS_INFO` | No modified executable pytest test | $0.004 | 278.929s |
| `openai/openai-guardrails-python` [#38](https://github.com/openai/openai-guardrails-python/issues/38) | `NEEDS_INFO` | No modified executable pytest test | $0.006 | 258.210s |

Distribution: **2 confirmations, 3 needs-information outcomes, 1
won't-reproduce, 0 not-a-bug**. Put another way, the system **declined to
confirm 4 of the 6 selected issues** and returned bounded non-confirming
outcomes instead. The six records used about **$0.03** in tracked OpenAI API
cost, about **46 seconds** of tracked OpenAI latency, and about **23 minutes**
of explicitly unpriced Codex execution.

Initial #3654 runs with isolated agent networking and an unsupported pip
`--group` setup command were retained as auditable environment/setup failures;
they are excluded from the table and distribution. The corrected runs used
explicit allowed network policy and repository-specific setup commands.

## 7. User experience

### Maintainer evidence viewer

The home screen is a triage queue, sorted to surface behavior-gap confirmations
first. It offers repository/issue, title, outcome, `assertsFailure`, timestamp,
duration, tracked cost/latency where available, filtering, accessible anchors,
copyable investigation IDs, horizontal overflow protection, and an empty state.

The detail view provides:

- GitHub issue link, outcome/status chips, validation reason, and an explainer
  that `assertsFailure` is set only by deterministic validation, never a model;
- attempt and timeline information without duplicate cards;
- honest unavailable values (em dash plus explanation), rather than fabricated
  zero cost or “not recorded” clutter;
- tabs for extraction JSON, git diff, pytest/Vitest output, terminal log, JUnit
  XML, and reproducibility manifest when available;
- line-level diff coloring, failed-line/summary emphasis, JSON formatting,
  per-artifact copy buttons, size/timestamp display, loading and unavailable
  states;
- a copyable, preview-only `NEEDS_INFO` maintainer response; and
- read-only related-investigation suggestions.

### Pilot reviewer experience

When explicitly enabled, a separate `/?reviewer=1` surface uses short-lived
server-side sessions, HttpOnly/SameSite cookies, and CSRF protection. It exposes
only repository-scoped work, has no direct “post to GitHub” action, and supports
append-only semantic assessments and posting approvals tied to exact immutable
evidence and comment previews. An authenticated weekly-report view shows only
aggregate, repository-scoped pilot inputs and caveats.

## 8. Safety, privacy, and GitHub trust boundary

### 8.1 Default posture

- GitHub issue retrieval is read-only.
- Public dashboard pages do not mutate data or invoke GitHub writes.
- Webhooks are disabled without an HMAC secret and repository allowlist.
- Auto-posting is disabled by default and dry-run by default.
- The demo has no credentials and cannot make live calls.

### 8.2 Commenting gates

Even when a repository deliberately enables the webhook worker, a public comment
requires global enablement, dry-run off, repository allowlisting, terminal
eligible investigation state, exact rendered preview, valid unconsumed
approval, and immediate pre-write revalidation. For a behavior-gap comment,
the current policy also requires unanimously aligned semantic review and a
maintainer or configured posting approver. `NEEDS_INFO` requires exact-preview
human approval. Other classifications and operational/flaky cases are forbidden.

Comments have hidden delivery markers and duplicate checks. Approval data binds
packet/version/hash, consensus snapshot/hash, normalized body hash,
classification/comment type, policy version, reviewer cohort/role, expiry, and
rationale. Any relevant change invalidates reuse.

### 8.3 Data minimization

Raw GitHub issue bodies are not persisted in review packets or semantic-corpus
exports. Review packets contain bounded extraction and evidence metadata, a
bounded diff excerpt, artifact IDs/paths/hashes, validation/classification, and
bounded comment preview. They exclude terminal logs, full repositories,
credentials, raw bodies, mutable GitHub fields, and unbounded content.

Pilot telemetry stores bounded milestone events and idle-capped active time. It
does not record keystrokes, mouse activity, browser history, full URLs, screen
content, raw rationales, tokens, or session secrets. Semantic-corpus export is
blocked without active, repository-specific `EVALUATION_ONLY` consent; consent
revocation blocks future exports but cannot erase copies already taken outside
the system.

## 9. Operations, scale, and cost controls

### Queueing

Webhook and batch work share persisted jobs with source, priority, attempts,
maximum attempts, lease owner/expiry, retry eligibility, backoff, queue depth,
and per-repository concurrency. States include `QUEUED`, `RUNNING`,
`SUCCEEDED`, `RETRY_SCHEDULED`, `FAILED`, `DEAD_LETTER`, and `CANCELLED`.
Webhook capacity saturation returns HTTP 429 rather than silently dropping a
signed delivery.

Current defaults are global concurrency 1, per-repository concurrency 1, queue
capacity 100, 30-minute lease, and three maximum job attempts. Batch work can
run inline or enqueue for workers. SQLite's implementation is appropriate for
one host only; horizontal production workers require a shared transactional
database such as PostgreSQL plus production row locking.

### Cost and budgets

Known-price OpenAI calls are reserved before invocation, reconciled to actual
locally priced usage, and released when unused. Default caps are $1.00 per
investigation, $20.00 per repository/day, $100.00 per repository/month, and a
$0.10 reservation per billable call. Unknown-price OpenAI calls are explicitly
`UNBUDGETABLE`, not reported as zero dollars.

Codex execution is capped by wall time (900 seconds per investigation by
default) and persists invocation count/seconds, but its dollar cost is unknown.
Claude Code follows the same unpriced-agent treatment until an attributable
billing source is available. Infrastructure cost, human-review labor cost, and
fully loaded COGS are not currently measured.

## 10. Evaluation and semantic-fidelity governance

The system recognizes the central trust problem: a generated test can fail
cleanly while still failing to encode the intended issue behavior. The pilot
workflow therefore separates mechanical validation from semantic fidelity.

Each packet can receive independent maintainer and independent-engineer labels
for extraction alignment, test alignment, failure-signal support, and comment
appropriateness. With one maintainer and two independent engineers, deterministic
consensus records `UNANIMOUSLY_ALIGNED`, `DISAGREED`, `REJECTED_ALIGNMENT`,
`INSUFFICIENT_CONTEXT`, or `UNAVAILABLE`. These records are append-only and
versioned; they do not change the original investigation verdict.

The measurement-only eligibility policy is intentionally strict: 300
adjudicated examples, required cohort coverage, zero material false-alignment
signals, no disagreement, and a one-sided 95% Wilson lower bound of at least
99%. Meeting it does not enable unattended posting or remove per-result
approval. The project has not yet collected a corpus sufficient to make any
precision, customer-value, or automated-posting claim.

## 11. Current limitations and risks

1. **Semantic truth remains human-reviewed.** Mechanical evidence is not a
   substitute for a maintainer's understanding of product intent.
2. **Live agent connectivity remains a trust boundary.** The separate agent
   container has provider egress and the Codex credential mount; focused tests
   and confirmations have neither and are network-isolated by default. This
   reduces test-execution exposure but does not remove agent-runtime risk for
   public or untrusted code.
3. **Live validation is deliberately scoped.** The cross-repository batch was
   selected from Python/JavaScript repositories compatible with the implemented
   pytest and Vitest adapters. Rust/Cargo and other runner ecosystems were out
   of scope for this validation, rather than treated as failed investigations.
4. **Environment setup remains repository-specific.** PEP 735 dependency groups
   exposed a concrete gap: pip cannot consume `--group`, so operators must
   supply an explicit setup command for such repositories.
5. **Scale is local-host bounded.** SQLite job claims/budgets are not a
   multi-instance production deployment strategy.
6. **No alternative provider performance claim.** Claude adapter architecture is
   present but no approved live comparison has run.
7. **No real commercial evidence yet.** There are no external design partners,
   retention results, willingness-to-pay data, or fully loaded COGS.
8. **Similarity is advisory.** It is not a duplicate decision engine and does
   not yet have vector indexing or maintainer confirm/dismiss controls.
9. **Replay is best-effort.** Registries, image digests, and dependencies can
   prevent exact reconstruction.

## 12. Validation baseline

The last recorded full verification baseline is:

```text
python3 -m pytest -q              175 passed, 1 skipped
dashboard tests                   22 tests across 11 files passed
dashboard production build        passed
git diff --check                  passed
```

The live cross-repository batch above is additional operational evidence; it is
not a substitute for a labelled semantic-fidelity evaluation or a security audit.

## 13. Recommended next work

1. Further harden agent egress: use a narrowly scoped egress
   channel or isolated agent service so ordinary test execution can remain
   network-disabled without breaking provider access.
2. Add first-class dependency-group setup support (for example an explicitly
   pinned sandbox toolchain) rather than requiring per-repository pip commands.
3. Recruit consented design partners and collect independently adjudicated
   semantic-review packets before considering any relaxation of posting policy.
4. Establish a real provider-comparison protocol and run it only with approved,
   consented examples and fixed budgets.
5. Move production queue/budget claims to PostgreSQL and add deployment,
   monitoring, retention, and incident procedures before multi-host operation.
6. Measure full COGS—including agent billing, infrastructure, and human review—
   alongside time-to-triage and maintainer acceptance outcomes.

## 14. Bottom line

EvidenceTrail is credible as an evidence-generation and maintainer-review tool:
it has real reproducible artifacts, a strict structured validation gate,
negative outcomes in live runs, clear cost provenance, and deliberately
constrained public-action controls. It is not yet credible to present as an
autonomous bug-deciding or broadly production-ready triage service. The next
proof point is not more labels; it is semantic-fidelity evidence from real
reviewers, improved sandbox trust boundaries, and measured maintainer value.
