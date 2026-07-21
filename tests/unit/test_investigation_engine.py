from pathlib import Path

import pytest
from sqlalchemy import select

from triage.domain.models import InvestigationEvidence, IssueExtraction
from triage.github.models import GitHubIssue
from triage.investigation.engine import InvestigationEngine, revision_reason_from_attempt
from triage.investigation.models import AttemptExecution
from triage.investigation.runner import attempt_artifact_dir
from triage.sandbox.manager import EnvironmentSetupFailure, SetupCommand
from triage.validation.models import ValidationResult
from triage.persistence.database import Base, create_session_factory
from triage.persistence.models import Artifact, Hypothesis, Investigation, LLMCall
from triage.persistence.repositories import ArtifactRepository, HypothesisRepository, InvestigationRepository, LLMCallRepository


class FakeRunner:
    def __init__(self, pytest_exit_codes: list[int]):
        self.pytest_exit_codes = pytest_exit_codes
        self.prompts: list[str] = []

    def run_attempt(self, repository_path: Path, prompt: str, artifact_dir: Path) -> AttemptExecution:
        self.prompts.append(prompt)
        artifact_dir.mkdir(parents=True)
        terminal = artifact_dir / "terminal.log"
        diff = artifact_dir / "git.diff"
        output = artifact_dir / "pytest_output.txt"
        terminal.write_text(f"terminal attempt {len(self.prompts)}", encoding="utf-8")
        diff.write_text("", encoding="utf-8")
        output.write_text("pytest output", encoding="utf-8")
        return AttemptExecution(
            InvestigationEvidence(
                asserts_failure=False,
                git_diff_path=diff,
                pytest_output_path=output,
                pytest_exit_code=self.pytest_exit_codes.pop(0),
            ),
            terminal,
            0,
            5,
        )


class FakeValidator:
    def __init__(self, results: list[bool]):
        self.results = results

    def validate(self, evidence):
        asserts_failure = self.results.pop(0)
        return ValidationResult(asserts_failure, "validator result", [], int(asserts_failure))


def issue() -> GitHubIssue:
    return GitHubIssue(
        repository="psf/requests", issue_number=123, title="Failure", body="Details", author="reporter",
        labels=[], comments=[], state="open", created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z", url="https://github.com/psf/requests/issues/123",
    )


def extraction() -> IssueExtraction:
    return IssueExtraction(
        summary="Failure", steps_to_reproduce=[], expected_behavior=None, actual_behavior=None,
        environment={}, affected_area=None, repro_code=None, missing_info=[], confidence=0.5,
    )


def engine_with(tmp_path, runner, validator):
    factory = create_session_factory(f"sqlite:///{tmp_path / 'triage.db'}")
    Base.metadata.create_all(factory.kw["bind"])
    session = factory()
    return (
        InvestigationEngine(
            runner, InvestigationRepository(session), HypothesisRepository(session), ArtifactRepository(session),
            LLMCallRepository(session), tmp_path / "artifacts",
            validator,
        ),
        session,
    )


def test_engine_stops_at_three_attempts_and_persists_adaptation(tmp_path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    runner = FakeRunner([0, 0, 0])
    engine, session = engine_with(tmp_path, runner, FakeValidator([False, False, False]))

    result = engine.investigate(issue(), extraction(), repository)

    assert result.completed is False
    assert len(result.attempts) == 3
    hypotheses = list(session.scalars(select(Hypothesis).order_by(Hypothesis.attempt_number)))
    assert hypotheses[0].revision_reason is None
    assert hypotheses[1].revision_reason is not None
    assert "Previous attempt made no repository changes" in runner.prompts[1]
    assert session.scalar(select(Investigation.status)) == "COMPLETED_NO_GAP"
    artifacts = list(session.scalars(select(Artifact)))
    assert len(artifacts) == 10
    assert any(artifact.kind == "extraction_json" for artifact in artifacts)
    calls = list(session.scalars(select(LLMCall)))
    assert len(calls) == 3
    assert all(call.provider == "codex" and call.pricing_version is None and call.cost_usd is None for call in calls)
    session.close()


def test_engine_stops_after_first_failing_pytest_result(tmp_path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    runner = FakeRunner([1])
    engine, session = engine_with(tmp_path, runner, FakeValidator([True]))

    result = engine.investigate(issue(), extraction(), repository)

    assert result.completed is True
    assert len(result.attempts) == 1
    assert session.scalar(select(Investigation.status)) == "COMPLETED"
    session.close()


def test_confirmation_runs_require_every_execution_to_agree(tmp_path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    runner = FakeRunner([1, 1])
    engine, session = engine_with(tmp_path, runner, FakeValidator([True, True]))
    engine.confirmation_runs = 2
    result = engine.investigate(issue(), extraction(), repository)
    assert result.completed is True
    assert len(result.attempts) == 2
    session.close()


def test_confirmation_disagreement_is_unstable_not_confirmed(tmp_path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    runner = FakeRunner([1, 0])
    engine, session = engine_with(tmp_path, runner, FakeValidator([True, False]))
    engine.confirmation_runs = 2
    result = engine.investigate(issue(), extraction(), repository)
    assert result.completed is False
    assert "FLAKY_OR_INCONCLUSIVE" in result.validation.reason
    assert session.scalar(select(Investigation.asserts_failure)) is False
    session.close()


def test_engine_does_not_complete_on_unvalidated_pytest_failure(tmp_path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    runner = FakeRunner([1, 0, 0])
    engine, session = engine_with(tmp_path, runner, FakeValidator([False, False, False]))

    result = engine.investigate(issue(), extraction(), repository)

    assert result.completed is False
    assert len(result.attempts) == 3
    assert session.scalar(select(Investigation.asserts_failure)) is False
    session.close()


def test_artifact_paths_and_revision_reason(tmp_path) -> None:
    path = attempt_artifact_dir(tmp_path, "run-1", 2)
    assert path == tmp_path / "run-1" / "attempt_2"
    path.mkdir(parents=True)
    diff = path / "git.diff"
    output = path / "pytest_output.txt"
    terminal = path / "terminal.log"
    diff.write_text("change", encoding="utf-8")
    output.write_text("passed", encoding="utf-8")
    terminal.write_text("terminal", encoding="utf-8")
    execution = AttemptExecution(
        InvestigationEvidence(
            asserts_failure=False, git_diff_path=diff, pytest_output_path=output, pytest_exit_code=0
        ),
        terminal,
        0,
        1,
    )
    assert "did not produce a failing pytest result" in revision_reason_from_attempt(execution)


def test_engine_persists_setup_failure_as_operational_evidence_without_validation(tmp_path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()

    class SetupFailingRunner:
        def run_attempt(self, repository_path, prompt, artifact_dir):
            artifact_dir.mkdir(parents=True)
            terminal = artifact_dir / "terminal.log"
            pytest_output = artifact_dir / "pytest_output.txt"
            diff = artifact_dir / "git.diff"
            terminal.write_text("ENVIRONMENT SETUP FAILURE", encoding="utf-8")
            pytest_output.write_text("", encoding="utf-8")
            diff.write_text("", encoding="utf-8")
            error = EnvironmentSetupFailure(
                "Environment setup failed: requirements.txt installation exited 1",
                SetupCommand("python -m pip install -r requirements.txt", "requirements.txt"),
            )
            error.execution = AttemptExecution(
                InvestigationEvidence(
                    asserts_failure=False,
                    git_diff_path=diff,
                    pytest_output_path=pytest_output,
                    pytest_exit_code=1,
                ),
                terminal,
                1,
                0,
            )
            raise error

    class NeverValidate:
        def validate(self, evidence):
            raise AssertionError("setup failure must not be classified or validated")

    engine, session = engine_with(tmp_path, SetupFailingRunner(), NeverValidate())
    with pytest.raises(EnvironmentSetupFailure):
        engine.investigate(issue(), extraction(), repository)
    investigation = session.scalar(select(Investigation))
    assert investigation.status == "FAILED"
    assert investigation.classification is None
    assert investigation.asserts_failure is False
    assert "Environment setup failed" in investigation.validation_reason
    assert {artifact.kind for artifact in session.scalars(select(Artifact))} >= {"extraction_json", "terminal_log", "pytest_output", "git_diff"}
    session.close()
