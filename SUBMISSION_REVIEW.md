# EvidenceTrail — Submission Review Packet

## Submission at a glance

- **Project name:** EvidenceTrail
- **Tagline:** Evidence, not guesses.
- **Repository:** https://github.com/NikhilPande008/github-issue-triage
- **Category:** Developer tool / GitHub issue investigation
- **Demo:** Local, no-key judge demo; YouTube link is in the Devpost submission.

## One-sentence pitch

EvidenceTrail turns GitHub issue reports into reproducible, evidence-backed investigations so maintainers can review tests, logs, and diffs instead of trusting an AI summary.

## The problem

Issue reports are often useful but incomplete. Before acting, maintainers need to know whether the described behavior is reproducible, what code path is relevant, whether a focused test captures the claim, and whether the result is an actual behavior gap rather than an environment or setup failure.

## The solution

EvidenceTrail runs a bounded, read-only investigation and saves an inspectable evidence trail:

1. Structured extraction of the issue report.
2. A focused test change proposed during investigation.
3. Terminal output, Git diff, and structured JUnit test results.
4. Deterministic validation and a conservative outcome for maintainer review.

It confirms a behavior gap only when executable evidence meets the validator's requirements. It does not decide whether the issue is a bug, feature request, documentation issue, or intended behavior.

## Demo path for reviewers

Use the committed demo snapshot. It needs no GitHub access, OpenAI key, Codex authentication, Docker, or rerunning a live investigation.

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

Open http://localhost:5173 and select **psf/requests #7564**.

## Recommended review flow

1. Open the triage queue and select `psf/requests #7564`.
2. Read the persisted issue extraction.
3. Inspect the focused test change in the Git diff.
4. Inspect the pytest output and structured JUnit XML.
5. Confirm the deterministic validation reason and `BEHAVIOR_GAP_CONFIRMED` outcome.
6. Open the timeline and reproducibility manifest to see how the evidence was preserved.

### What the flagship example demonstrates

The issue requests `FileNotFoundError` for missing TLS material. The focused changed test requires `FileNotFoundError`, `errno.ENOENT`, and the filename. The current implementation raises `OSError`, so the focused test fails. The validator uses the changed executable test and valid structured failure evidence to confirm that the requested behavior is absent.

## How OpenAI tools were used

- **Codex:** locating relevant code paths, proposing focused executable test changes, running targeted tests, and retaining execution artifacts.
- **GPT-5.6:** structured issue extraction and evidence classification.
- **Deterministic validation:** gates `BEHAVIOR_GAP_CONFIRMED`; model output alone cannot create this verdict.

## Technical design

- Python, FastAPI, SQLAlchemy, SQLite
- React, TypeScript, Vite
- Docker-isolated live investigation containers
- Pytest and Vitest runner adapters
- JUnit XML as the authoritative structured test-result input
- GitHub REST access is read-only by default

## Key trust boundaries

- Fresh repository clones and short-lived, non-privileged Docker containers are used for live investigations.
- GitHub write actions are not exposed in the public dashboard.
- Setup failures, timeouts, malformed output, flaky confirmations, and insufficient issue details receive conservative/inconclusive outcomes rather than a behavior-gap confirmation.
- Evidence artifacts are persisted for review instead of replaced by a prose-only conclusion.

## Reviewer questions

1. Is the evidence trail understandable without reading the source code?
2. Does the distinction between "behavior is absent" and "this is definitely a bug" come through clearly?
3. Are the test output, diff, and validation details easy to find?
4. Does the no-key local demo make the project straightforward to evaluate?
5. Is any important trust or workflow information missing from the dashboard or README?

## Submission assets

- **Video:** show dashboard overview, `psf/requests #7564`, extraction, diff, test evidence, deterministic verdict, then the Codex/GPT-5.6 roles.
- **Gallery:** dashboard overview; flagship investigation; evidence/artifacts; timeline; reproducibility information; optional architecture diagram.

## Pre-review consistency check

All public submission surfaces should use **EvidenceTrail**: Devpost, repository metadata, README, dashboard, video title, and screenshot gallery.
