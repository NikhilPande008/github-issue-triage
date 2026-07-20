from pathlib import Path
from typing import Protocol

from triage.core.run_id import new_run_id
from triage.domain.enums import InvestigationStatus
from triage.domain.models import IssueExtraction
from triage.github.models import GitHubIssue
from triage.investigation.models import AttemptExecution, AttemptRecord, InvestigationResult
from triage.investigation.prompts import render_codex_prompt
from triage.investigation.runner import attempt_artifact_dir
from triage.persistence.models import Artifact, Hypothesis, Investigation, LLMCall
from triage.validation.models import ValidationEvidence, ValidationResult

MAX_ATTEMPTS = 3


class InvestigationRunner(Protocol):
    def run_attempt(self, repository_path: Path, prompt: str, artifact_dir: Path) -> AttemptExecution: ...


class Store(Protocol):
    def create(self, item): ...

    def update(self, item, **values): ...


class Validator(Protocol):
    def validate(self, evidence: ValidationEvidence) -> ValidationResult: ...


def revision_reason_from_attempt(execution: AttemptExecution) -> str:
    if execution.codex_exit_code != 0:
        return "Previous Codex invocation exited nonzero; revise from its terminal evidence."
    if execution.evidence.git_diff_path and not execution.evidence.git_diff_path.read_text(encoding="utf-8").strip():
        return "Previous attempt made no repository changes; target a more concrete reproduction path."
    if execution.evidence.pytest_exit_code == 0:
        return "Previous attempt did not produce a failing pytest result; revise the hypothesis using its test evidence."
    return "Previous attempt ended without a conclusive result; revise from the captured evidence."


class InvestigationEngine:
    """Bounded investigation orchestration; evidence validation controls completion."""

    def __init__(self, runner: InvestigationRunner, investigations: Store, hypotheses: Store, artifacts: Store, llm_calls: Store, artifacts_root: Path, validator: Validator):
        self.runner = runner
        self.investigations = investigations
        self.hypotheses = hypotheses
        self.artifacts = artifacts
        self.llm_calls = llm_calls
        self.artifacts_root = artifacts_root
        self.validator = validator

    def investigate(self, issue: GitHubIssue, extraction: IssueExtraction, repository_path: Path) -> InvestigationResult:
        investigation = self.investigations.create(
            Investigation(repository=issue.repository, issue_number=issue.issue_number, status=InvestigationStatus.PENDING)
        )
        self.investigations.update(investigation, status=InvestigationStatus.RUNNING)
        run_id = new_run_id()
        extraction_path = self.artifacts_root / run_id / "extraction.json"
        extraction_path.parent.mkdir(parents=True, exist_ok=True)
        extraction_path.write_text(extraction.model_dump_json(indent=2), encoding="utf-8")
        self.artifacts.create(
            Artifact(investigation_id=investigation.id, kind="extraction_json", path=str(extraction_path))
        )
        attempts: list[AttemptRecord] = []
        revision_reason: str | None = None
        previous_evidence = ""
        validation: ValidationResult | None = None

        for attempt_number in range(1, MAX_ATTEMPTS + 1):
            hypothesis = self._hypothesis(extraction, attempt_number)
            self.hypotheses.create(
                Hypothesis(
                    investigation_id=investigation.id,
                    attempt_number=attempt_number,
                    statement=hypothesis,
                    revision_reason=revision_reason,
                )
            )
            prompt = render_codex_prompt(extraction, attempt_number, revision_reason, previous_evidence)
            artifact_dir = attempt_artifact_dir(self.artifacts_root, run_id, attempt_number)
            execution = self.runner.run_attempt(repository_path, prompt, artifact_dir)
            self._record_attempt_artifacts(investigation.id, execution)
            self._record_codex_call(investigation.id, execution)
            validation = self.validator.validate(
                ValidationEvidence(
                    git_diff_path=execution.evidence.git_diff_path,
                    pytest_output_path=execution.evidence.pytest_output_path,
                    pytest_exit_code=execution.evidence.pytest_exit_code,
                )
            )
            self.investigations.update(
                investigation,
                asserts_failure=validation.asserts_failure,
                validation_reason=validation.reason,
            )
            record = AttemptRecord(attempt_number, hypothesis, revision_reason, execution, validation)
            attempts.append(record)
            if validation.asserts_failure:
                self.investigations.update(investigation, status=InvestigationStatus.COMPLETED)
                return InvestigationResult(investigation.id, run_id, True, attempts, validation)
            revision_reason = revision_reason_from_attempt(execution) + " Validation: " + validation.reason
            previous_evidence = execution.terminal_log_path.read_text(encoding="utf-8")

        self.investigations.update(investigation, status=InvestigationStatus.FAILED)
        assert validation is not None
        return InvestigationResult(investigation.id, run_id, False, attempts, validation)

    @staticmethod
    def _hypothesis(extraction: IssueExtraction, attempt_number: int) -> str:
        basis = extraction.summary or extraction.actual_behavior or "the reported issue"
        return f"Attempt {attempt_number}: reproduce {basis} with a focused pytest test."

    def _record_attempt_artifacts(self, investigation_id: str, execution: AttemptExecution) -> None:
        self.artifacts.create(Artifact(investigation_id=investigation_id, kind="terminal_log", path=str(execution.terminal_log_path)))
        self.artifacts.create(Artifact(investigation_id=investigation_id, kind="pytest_output", path=str(execution.evidence.pytest_output_path)))
        if execution.evidence.git_diff_path:
            self.artifacts.create(Artifact(investigation_id=investigation_id, kind="git_diff", path=str(execution.evidence.git_diff_path)))

    def _record_codex_call(self, investigation_id: str, execution: AttemptExecution) -> None:
        self.llm_calls.create(
            LLMCall(
                investigation_id=investigation_id,
                model="codex",
                purpose="investigation",
                input_tokens=0,
                cached_input_tokens=0,
                output_tokens=0,
                cost_usd=0,
                latency_ms=execution.codex_latency_ms,
            )
        )
