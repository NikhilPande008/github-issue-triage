# Submission checklist

## Offline demo startup

```bash
uv sync
uv run python scripts/validate_demo_seed.py
uv run python scripts/seed_demo.py --force
uv run uvicorn triage.api.main:app --reload
```

In a second terminal:

```bash
cd dashboard
npm install
npm run dev
```

Required routes: `/?brief=1`, `/?results=1`, and `/`.

## 60-second walkthrough

1. Open Evidence Brief and follow report → focused test → structured proof →
   bounded decision.
2. Open the complete evidence trail for the selected record.
3. Open Evidence Results and inspect confirmed, `NEEDS_INFO`, and
   `WONT_REPRO`/`COMPLETED_NO_GAP` examples.
4. Open the triage queue and a detail page; use browser Back and the header
   links to return.

Behavior gap confirmed means a focused test confirms the reported behavior is
absent in the inspected revision. It is not a bug, regression, or intent
decision.

Non-confirming outcomes are evidence-bounded and do not invalidate an issue.
`COMPLETED_NO_GAP` is a normal terminal review status; operational failures are
separate. The offline demo uses persisted snapshots only: it needs no
credentials and performs no GitHub writes, model calls, Codex calls, Docker
work, or external network access after seeding.

For live runs, focused tests and confirmation execution have no agent credential
mount and are network-isolated by default. The separate agent phase still needs
provider connectivity; this reduces test-execution exposure but is not a
complete solution to agent-runtime supply-chain or credential risk.

## Final verification

```bash
python3 scripts/validate_demo_seed.py
python3 -m pytest -q
cd dashboard && npm test -- --run
cd dashboard && npm run build
git diff --check
```
