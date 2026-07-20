import json
from contextlib import nullcontext

from triage import cli
from triage.domain.models import InvestigationEvidence
from triage.investigation.models import AttemptExecution, AttemptRecord
from triage.domain.models import IssueExtraction
from triage.investigation.models import InvestigationResult
from triage.validation.models import ValidationResult
from triage.github.models import GitHubIssue


def test_fetch_command_prints_normalized_json(monkeypatch, capsys) -> None:
    issue = GitHubIssue(
        repository="psf/requests",
        issue_number=123,
        title="Title",
        body="Body",
        author="author",
        labels=["bug"],
        comments=[],
        state="open",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        url="https://github.com/psf/requests/issues/123",
    )

    class FakeService:
        def __init__(self, client):
            pass

        def fetch_issue(self, issue_number: int) -> GitHubIssue:
            assert issue_number == 123
            return issue

    monkeypatch.setattr(cli, "GitHubIssueService", FakeService)
    assert cli.main(["fetch", "123"]) == 0
    assert json.loads(capsys.readouterr().out)["issue_number"] == 123


def test_extract_command_prints_validated_json(monkeypatch, capsys) -> None:
    issue = GitHubIssue(
        repository="psf/requests", issue_number=123, title="Title", body="Body", author="author",
        labels=[], comments=[], state="open", created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z", url="https://github.com/psf/requests/issues/123",
    )

    class FakeGitHubService:
        def __init__(self, client):
            pass

        def fetch_issue(self, issue_number: int) -> GitHubIssue:
            return issue

    class FakeExtractionService:
        def __init__(self, client, repository):
            pass

        def extract(self, fetched_issue: GitHubIssue) -> IssueExtraction:
            return IssueExtraction(
                summary="Title", steps_to_reproduce=[], expected_behavior=None, actual_behavior=None,
                environment={}, affected_area=None, repro_code=None, missing_info=["steps"], confidence=0.5,
            )

    class FakeSession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    monkeypatch.setattr(cli, "GitHubIssueService", FakeGitHubService)
    monkeypatch.setattr(cli, "ExtractionService", FakeExtractionService)
    monkeypatch.setattr(cli, "OpenAIExtractionClient", lambda key: object())
    monkeypatch.setattr(cli, "LLMCallRepository", lambda session: object())
    monkeypatch.setattr(cli, "create_session_factory", lambda url: lambda: FakeSession())
    assert cli.main(["extract", "123"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"] == "Title"


def test_investigate_local_command_prints_summary(monkeypatch, capsys, tmp_path) -> None:
    issue = GitHubIssue(
        repository="psf/requests", issue_number=123, title="Title", body="Body", author="author",
        labels=[], comments=[], state="open", created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z", url="https://github.com/psf/requests/issues/123",
    )

    class FakeGitHubService:
        def __init__(self, client):
            pass

        def fetch_issue(self, issue_number: int) -> GitHubIssue:
            return issue

    class FakeExtractionService:
        def __init__(self, client, repository):
            pass

        def extract(self, fetched_issue: GitHubIssue) -> IssueExtraction:
            return IssueExtraction(
                summary="Title", steps_to_reproduce=[], expected_behavior=None, actual_behavior=None,
                environment={}, affected_area=None, repro_code=None, missing_info=[], confidence=0.5,
            )

    class FakeEngine:
        def __init__(self, **kwargs):
            pass

        def investigate(self, fetched_issue, extraction, repository_path):
            pytest_output = tmp_path / "pytest_output.txt"
            pytest_output.write_text("1 failed\n", encoding="utf-8")
            git_diff = tmp_path / "git.diff"
            git_diff.write_text("diff --git a/tests/test_example.py b/tests/test_example.py\n", encoding="utf-8")
            terminal_log = tmp_path / "terminal.log"
            terminal_log.write_text("", encoding="utf-8")
            execution = AttemptExecution(
                evidence=InvestigationEvidence(
                    asserts_failure=True,
                    git_diff_path=git_diff,
                    pytest_output_path=pytest_output,
                    pytest_exit_code=1,
                ),
                terminal_log_path=terminal_log,
                codex_exit_code=0,
                codex_latency_ms=0,
            )
            return InvestigationResult(
                "investigation-1", "run-1", True,
                [AttemptRecord(1, "hypothesis", None, execution, ValidationResult(True, "validated", [], 1))],
                ValidationResult(True, "validated", [], 1),
            )

    class FakeInvestigationRepository:
        def __init__(self, session):
            pass

        def get(self, item_id):
            return object()

        def update(self, item, **values):
            assert values["classification"].value == "REPRODUCED"
            return item

    class FakeSession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    monkeypatch.setattr(cli, "GitHubIssueService", FakeGitHubService)
    monkeypatch.setattr(cli, "ExtractionService", FakeExtractionService)
    monkeypatch.setattr(cli, "InvestigationEngine", FakeEngine)
    monkeypatch.setattr(cli, "OpenAIExtractionClient", lambda key: object())
    monkeypatch.setattr(cli, "LLMCallRepository", lambda session: object())
    monkeypatch.setattr(cli, "InvestigationRepository", FakeInvestigationRepository)
    monkeypatch.setattr(cli, "HypothesisRepository", lambda session: object())
    monkeypatch.setattr(cli, "ArtifactRepository", lambda session: object())
    monkeypatch.setattr(cli, "create_session_factory", lambda url: lambda: FakeSession())
    monkeypatch.setattr(cli, "_runner_context", lambda settings: nullcontext(object()))
    assert cli.main(["investigate", "123"]) == 0
    assert capsys.readouterr().out == (
        "Investigation Complete\nassertsFailure: TRUE\nReason:\nvalidated\nClassification:\nREPRODUCED\n"
    )
