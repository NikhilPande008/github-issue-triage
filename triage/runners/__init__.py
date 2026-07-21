"""Deterministic test-runner adapters.

Implemented: pytest and Vitest.  Jest, Go, JUnit, and RSpec are future adapter
targets only; selecting them intentionally fails rather than guessing.
"""

from triage.runners.adapters import RunnerAdapter, RunnerSelectionError, select_runner

__all__ = ["RunnerAdapter", "RunnerSelectionError", "select_runner"]
