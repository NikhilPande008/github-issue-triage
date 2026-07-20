from dataclasses import dataclass
from pathlib import Path

from triage.domain.models import InvestigationEvidence
from triage.validation.models import ValidationResult


@dataclass(frozen=True)
class AttemptExecution:
    evidence: InvestigationEvidence
    terminal_log_path: Path
    codex_exit_code: int
    codex_latency_ms: int


@dataclass(frozen=True)
class AttemptRecord:
    attempt_number: int
    hypothesis: str
    revision_reason: str | None
    execution: AttemptExecution
    validation: ValidationResult


@dataclass(frozen=True)
class InvestigationResult:
    investigation_id: str
    run_id: str
    completed: bool
    attempts: list[AttemptRecord]
    validation: ValidationResult
