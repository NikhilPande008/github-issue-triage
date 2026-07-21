# Offline judge demo

This committed, read-only snapshot contains five selectively exported persisted
investigations and 68 referenced artifacts. It includes:

- `psf/requests` #7564 — modern `BEHAVIOR_GAP_CONFIRMED` flagship case,
  with exact pytest-target selection, structured JUnit evidence,
  proof-integrity evidence, and persisted confirmation provenance.
- `openai/openai-agents-python` #3563 — cross-repository
  `BEHAVIOR_GAP_CONFIRMED` case.
- `openai/openai-guardrails-python` #70 — cross-repository
  `BEHAVIOR_GAP_CONFIRMED` case.
- `openai/openai-agents-python` #3611 — `NEEDS_INFO` case.
- `openai/openai-agents-python` #3654 — `WONT_REPRO` case with
  `COMPLETED_NO_GAP` status.

All entries are persisted evidence snapshots, not fresh live runs. The demo
performs no GitHub, model, Docker, Codex, or OpenAI calls, and has no API keys
or credentials.

```bash
uv sync
uv run python scripts/validate_demo_seed.py
uv run python scripts/seed_demo.py --force
uv run uvicorn triage.api.main:app --reload
```

In another terminal:

```bash
cd dashboard
npm install
npm run dev
```

Open <http://localhost:5173/?brief=1> for the Evidence Brief,
<http://localhost:5173/?results=1> for Evidence Results, or
<http://localhost:5173/> for the triage queue.

`BEHAVIOR_GAP_CONFIRMED` means deterministic structured validation found a
clean focused failing test in the inspected revision. It does not decide
whether a report is a bug, regression, intended behavior, or valid issue.
The refreshed Requests example demonstrates that reported behavior differs from
the generated focused test expectation; it does not determine intended
behavior, regression status, or maintainer priority.
Non-confirming outcomes are evidence-bounded and likewise do not invalidate an
issue. The snapshot remains read-only.

The machine-readable [manifest](seed/demo-manifest.json) lists only selected
IDs, public issue metadata, classifications, purpose, and artifact counts.
Maintainers refresh the seed with `scripts/export_demo.py`, explicitly naming
investigation IDs; it never copies the live database wholesale.
