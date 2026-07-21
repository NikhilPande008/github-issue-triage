import json
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
from triage.sandbox.manager import EnvironmentSetupFailure
from triage.validation.models import ValidationEvidence, ValidationResult
from triage.validation.proof_integrity import analyze as analyze_proof_integrity, write_report

MAX_ATTEMPTS = 3


def _selection(path: Path | None) -> dict | None:
    if path is None: return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


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
        return "Previous attempt made no repository changes; target a more concrete behavior specification."
    if execution.evidence.pytest_exit_code == 0:
        return "Previous attempt did not produce a failing pytest result; revise the hypothesis using its test evidence."
    return "Previous attempt ended without a conclusive result; revise from the captured evidence."


class InvestigationEngine:
    """Bounded investigation orchestration; evidence validation controls completion."""

    def __init__(self, runner: InvestigationRunner, investigations: Store, hypotheses: Store, artifacts: Store, llm_calls: Store, artifacts_root: Path, validator: Validator, confirmation_runs: int = 1, budget=None):
        self.runner = runner
        self.investigations = investigations
        self.hypotheses = hypotheses
        self.artifacts = artifacts
        self.llm_calls = llm_calls
        self.artifacts_root = artifacts_root
        self.validator = validator
        self.confirmation_runs = max(1, confirmation_runs)
        self.budget = budget

    def investigate(
        self, issue: GitHubIssue, extraction: IssueExtraction, repository_path: Path, investigation: Investigation | None = None
    ) -> InvestigationResult:
        investigation = investigation or self.investigations.create(
            Investigation(repository=issue.repository, issue_number=issue.issue_number, issue_title=issue.title, status=InvestigationStatus.PENDING)
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
            try:
                if self.budget:
                    self.budget.before_codex(investigation.id)
                execution = self.runner.run_attempt(repository_path, prompt, artifact_dir)
            except EnvironmentSetupFailure as error:
                if error.execution is not None:
                    self._record_attempt_artifacts(investigation.id, error.execution)
                self.investigations.update(
                    investigation,
                    status=InvestigationStatus.FAILED,
                    asserts_failure=False,
                    validation_reason=str(error),
                )
                raise
            self._record_attempt_artifacts(investigation.id, execution)
            proof_report = analyze_proof_integrity(execution.evidence.git_diff_path, execution.evidence.runner_id, extraction)
            proof_path = write_report(proof_report, artifact_dir / "proof_integrity.json")
            self.artifacts.create(Artifact(investigation_id=investigation.id, kind="proof_integrity_report", path=str(proof_path)))
            if investigation.test_runner != execution.evidence.runner_id:
                self.investigations.update(investigation, test_runner=execution.evidence.runner_id)
            self._record_codex_call(investigation.id, attempt_number, execution)
            if self.budget:
                self.budget.record_codex(investigation.id, execution.codex_latency_ms)
            # The runner adapter remains the deterministic authority for a
            # behavior-gap confirmation; the LLM classifier only consumes this evidence later.
            validation = self.validator.validate(
                ValidationEvidence(
                    git_diff_path=execution.evidence.git_diff_path,
                    pytest_output_path=execution.evidence.pytest_output_path,
                    pytest_exit_code=execution.evidence.pytest_exit_code,
                    runner_id=execution.evidence.runner_id,
                    structured_results_path=execution.evidence.structured_results_path,
                    focused_test_selection=_selection(execution.evidence.focused_test_selection_path),
                    focused_test_selection_required=True,
                    execution_failure_reason=execution.evidence.execution_failure_reason,
                    reliability_status=execution.evidence.reliability_status,
                    proof_integrity_report=proof_report,
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
                if not self._confirm_stable(repository_path, prompt, run_id, investigation, attempts, validation):
                    unstable = ValidationResult(False, "FLAKY_OR_INCONCLUSIVE: confirmation execution did not reproduce a clean structured test failure.", [], 0)
                    self.investigations.update(investigation, status=InvestigationStatus.FAILED, asserts_failure=False, validation_reason=unstable.reason)
                    return InvestigationResult(investigation.id, run_id, False, attempts, unstable)
                self.investigations.update(investigation, status=InvestigationStatus.COMPLETED)
                return InvestigationResult(investigation.id, run_id, True, attempts, validation)
            revision_reason = revision_reason_from_attempt(execution) + " Validation: " + validation.reason
            if proof_report["result"] == "REJECTED_PROOF_PATTERN": revision_reason += " Proof integrity: " + validation.reason
            previous_evidence = execution.terminal_log_path.read_text(encoding="utf-8")

        # Exhausting focused attempts is a completed evidence review, not an
        # operational failure. The classifier will attach a conservative
        # non-confirming outcome after this method returns.
        self.investigations.update(investigation, status=InvestigationStatus.COMPLETED_NO_GAP)
        assert validation is not None
        return InvestigationResult(investigation.id, run_id, False, attempts, validation)

    def _confirm_stable(self, repository_path: Path, prompt: str, run_id: str, investigation: Investigation, attempts: list[AttemptRecord], initial: ValidationResult) -> bool:
        """Never retry-until-green: every configured replay must independently agree."""
        for confirmation_number in range(2, self.confirmation_runs + 1):
            artifact_dir = attempt_artifact_dir(self.artifacts_root, run_id, len(attempts) + 1)
            try:
                if self.budget:
                    self.budget.before_codex(investigation.id)
                confirm = getattr(self.runner, "run_confirmation", self.runner.run_attempt)
                execution = confirm(repository_path, "Confirmation execution: " + prompt, artifact_dir)
            except Exception:
                return False
            self._record_attempt_artifacts(investigation.id, execution)
            self._record_codex_call(investigation.id, len(attempts) + 1, execution)
            if self.budget:
                self.budget.record_codex(investigation.id, execution.codex_latency_ms)
            validation = self.validator.validate(
                ValidationEvidence(
                    git_diff_path=execution.evidence.git_diff_path,
                    pytest_output_path=execution.evidence.pytest_output_path,
                    pytest_exit_code=execution.evidence.pytest_exit_code,
                    runner_id=execution.evidence.runner_id,
                    structured_results_path=execution.evidence.structured_results_path,
                    focused_test_selection=_selection(execution.evidence.focused_test_selection_path),
                    focused_test_selection_required=True,
                    execution_failure_reason=execution.evidence.execution_failure_reason,
                    reliability_status="CONFIRMATION",
                )
            )
            attempts.append(AttemptRecord(len(attempts) + 1, "Confirmation execution", None, execution, validation))
            if not validation.asserts_failure:
                return False
        return True

    @staticmethod
    def _hypothesis(extraction: IssueExtraction, attempt_number: int) -> str:
        basis = extraction.summary or extraction.actual_behavior or "the reported issue"
        return f"Attempt {attempt_number}: test whether {basis} is absent with a focused pytest test."

    def _record_attempt_artifacts(self, investigation_id: str, execution: AttemptExecution) -> None:
        self.artifacts.create(Artifact(investigation_id=investigation_id, kind="terminal_log", path=str(execution.terminal_log_path)))
        output_kind = "pytest_output" if execution.evidence.runner_id == "pytest" else f"{execution.evidence.runner_id}_output"
        self.artifacts.create(Artifact(investigation_id=investigation_id, kind=output_kind, path=str(execution.evidence.pytest_output_path)))
        if execution.evidence.structured_results_path is not None:
            self.artifacts.create(Artifact(investigation_id=investigation_id, kind="structured_test_results_junit", path=str(execution.evidence.structured_results_path)))
        if execution.evidence.reproducibility_manifest_path is not None:
            self.artifacts.create(Artifact(investigation_id=investigation_id, kind="reproducibility_manifest", path=str(execution.evidence.reproducibility_manifest_path)))
        if execution.evidence.focused_test_selection_path is not None:
            self.artifacts.create(Artifact(investigation_id=investigation_id, kind="focused_test_selection", path=str(execution.evidence.focused_test_selection_path)))
        if execution.evidence.git_diff_path:
            self.artifacts.create(Artifact(investigation_id=investigation_id, kind="git_diff", path=str(execution.evidence.git_diff_path)))

    def _record_codex_call(self, investigation_id: str, attempt_number: int, execution: AttemptExecution) -> None:
        self.llm_calls.create(
            LLMCall(
                investigation_id=investigation_id,
                attempt_number=attempt_number,
                provider="codex",
                model="codex",
                pricing_version=None,
                purpose="investigation",
                input_tokens=0,
                cached_input_tokens=0,
                output_tokens=0,
                # Codex does not provide billing data to this application.
                # Unknown cost must remain unavailable, never synthetic zero.
                cost_usd=None,
                latency_ms=execution.codex_latency_ms,
            )
        )
