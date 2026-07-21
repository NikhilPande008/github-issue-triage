import json
from contextlib import nullcontext

from triage import cli
from triage.batch import BatchItem, BatchSummary
from triage.domain.enums import Classification
from triage.domain.models import InvestigationEvidence
from triage.investigation.models import AttemptExecution, AttemptRecord
from triage.domain.models import IssueExtraction
from triage.investigation.models import InvestigationResult
from triage.validation.models import ValidationResult
from triage.github.models import GitHubIssue
from triage.github.client import GitHubRateLimitError


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
        def __init__(self, client, repository, investigation_id=None):
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
        def __init__(self, client, repository, investigation_id=None):
            pass

        def extract(self, fetched_issue: GitHubIssue) -> IssueExtraction:
            return IssueExtraction(
                summary="Title", steps_to_reproduce=[], expected_behavior=None, actual_behavior=None,
                environment={}, affected_area=None, repro_code=None, missing_info=[], confidence=0.5,
            )

    class FakeEngine:
        def __init__(self, **kwargs):
            pass

        def investigate(self, fetched_issue, extraction, repository_path, investigation=None):
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

        def create(self, item):
            item.id = "investigation-1"
            return item

        def get(self, item_id):
            return object()

        def update(self, item, **values):
            if "classification" in values:
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


def test_batch_command_exits_cleanly_before_processing_when_candidate_fetch_is_rate_limited(monkeypatch, capsys) -> None:
    class FakeSession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    class FakeInvestigationRepository:
        def __init__(self, session):
            pass

        @property
        def processed_issue_numbers(self):
            return lambda repository: set()

    class RateLimitedBatchService:
        def __init__(self, *args):
            pass

        def run(self, *args, **kwargs):
            raise GitHubRateLimitError(
                "GitHub API rate limit exhausted. Set GITHUB_TOKEN to increase GitHub API rate limits."
            )

    monkeypatch.setattr(cli, "create_session_factory", lambda url: lambda: FakeSession())
    monkeypatch.setattr(cli, "InvestigationRepository", FakeInvestigationRepository)
    monkeypatch.setattr(cli, "BatchTriageService", RateLimitedBatchService)

    assert cli.main(["batch-triage", "--count", "5"]) == 2
    assert capsys.readouterr().out == (
        "Unable to select batch candidates: GitHub API rate limit exhausted. "
        "Set GITHUB_TOKEN to increase GitHub API rate limits.\n"
    )


def test_batch_summary_reports_queue_exhaustion_shortfall(capsys) -> None:
    summary = BatchSummary(
        items=[BatchItem(issue=GitHubIssue(
            repository="psf/requests", issue_number=1, title="Title", body="", author="author", labels=[], comments=[],
            state="open", created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z",
            url="https://github.com/psf/requests/issues/1",
        ), investigation_id="run-1", classification=Classification.NEEDS_INFO, duration_seconds=1, cost_usd=None)],
        requested_count=5, selected_count=1, skipped_count=3, pages_scanned=3, selection_end="queue exhausted",
    )
    cli._print_batch_summary(summary)
    output = capsys.readouterr().out
    assert "Selection: requested 5 new issues; selected 1; skipped 3 already processed; scanned 3 pages; queue exhausted." in output
    assert "Requested 5 new issues; found 1 eligible unprocessed issues after scanning 3 pages (queue exhausted)." in output


def test_batch_summary_reports_scan_limit_shortfall_with_action(capsys) -> None:
    summary = BatchSummary([], requested_count=5, selected_count=0, skipped_count=100, pages_scanned=1, selection_end="scan-page limit reached")
    cli._print_batch_summary(summary)
    assert capsys.readouterr().out.endswith(
        "Requested 5 new issues; found 0 eligible unprocessed issues after scanning 1 pages "
        "(scan-page limit reached). Try --start-page, a smaller count, or GITHUB_TOKEN.\n"
    )
