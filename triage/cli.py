import argparse
import json
from contextlib import nullcontext
from collections.abc import Sequence
from datetime import datetime, timezone

from triage.classification.client import MODEL as CLASSIFICATION_MODEL, OpenAIClassificationClient
from triage.classification.models import ClassificationEvidence
from triage.classification.service import ClassificationService
from triage.batch import BatchItem, BatchTriageService, DEFAULT_BATCH_SIZE, MAX_BATCH_SIZE
from triage.config.settings import Settings
from triage.domain.enums import InvestigationStatus
from triage.extraction.client import OpenAIExtractionClient
from triage.extraction.service import ExtractionService
from triage.github.client import GitHubClient
from triage.github.service import GitHubIssueService
from triage.investigation.engine import InvestigationEngine
from triage.investigation.runner import LocalInvestigationRunner
from triage.persistence.database import create_session_factory
from triage.persistence.models import Investigation
from triage.persistence.repositories import ArtifactRepository, HypothesisRepository, InvestigationRepository, LLMCallRepository
from triage.sandbox.manager import SandboxManager
from triage.sandbox.runner import DockerInvestigationRunner
from triage.validation.validator import EvidenceValidator


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="triage")
    subparsers = parser.add_subparsers(dest="command", required=True)
    fetch = subparsers.add_parser("fetch", help="Fetch and normalize a GitHub issue")
    fetch.add_argument("issue_number", type=int)
    extract = subparsers.add_parser("extract", help="Extract a reproduction specification from a GitHub issue")
    extract.add_argument("issue_number", type=int)
    investigate = subparsers.add_parser("investigate", help="Run bounded Codex investigation in Docker")
    investigate.add_argument("issue_number", type=int)
    batch = subparsers.add_parser("batch-triage", help="Sequentially investigate newest open GitHub issues")
    batch.add_argument("--repository", default=None, help="Repository to triage (defaults to DEMO_REPOSITORY)")
    batch.add_argument("--count", type=int, default=DEFAULT_BATCH_SIZE, help=f"Issues to select (1-{MAX_BATCH_SIZE})")
    batch.add_argument("--start-page", type=int, default=1, help="GitHub open-issues page to start from")
    batch.add_argument("--force", action="store_true", help="Reprocess issues that already have a completed/failed investigation")
    args = parser.parse_args(argv)

    if args.command == "fetch":
        settings = Settings()
        service = GitHubIssueService(GitHubClient(settings.demo_repository, settings.github_token))
        issue = service.fetch_issue(args.issue_number)
        print(json.dumps(issue.model_dump(mode="json"), indent=2))
        return 0
    if args.command == "extract":
        settings = Settings()
        issue = GitHubIssueService(
            GitHubClient(settings.demo_repository, settings.github_token)
        ).fetch_issue(args.issue_number)
        session_factory = create_session_factory(settings.database_url)
        with session_factory() as session:
            extraction = ExtractionService(
                OpenAIExtractionClient(settings.openai_api_key), LLMCallRepository(session)
            ).extract(issue)
        print(json.dumps(extraction.model_dump(mode="json"), indent=2))
        return 0
    if args.command == "investigate":
        settings = Settings()
        issue = GitHubIssueService(
            GitHubClient(settings.demo_repository, settings.github_token)
        ).fetch_issue(args.issue_number)
        session_factory = create_session_factory(settings.database_url)
        with session_factory() as session:
            llm_calls = LLMCallRepository(session)
            investigations = InvestigationRepository(session)
            investigation = _start_investigation(investigations, issue)
            try:
                extraction = ExtractionService(
                    OpenAIExtractionClient(settings.openai_api_key), llm_calls, investigation.id
                ).extract(issue)
                with _runner_context(settings) as runner:
                    result = InvestigationEngine(
                        runner=runner,
                        investigations=investigations,
                        hypotheses=HypothesisRepository(session),
                        artifacts=ArtifactRepository(session),
                        llm_calls=llm_calls,
                        artifacts_root=settings.artifacts_dir,
                        validator=EvidenceValidator(),
                    ).investigate(issue, extraction, settings.local_repository_path, investigation)
                latest_attempt = result.attempts[-1] if result.attempts else None
                if latest_attempt is None:
                    raise RuntimeError("Investigation produced no execution evidence for classification")
                classification = ClassificationService(
                    OpenAIClassificationClient(settings.openai_api_key), llm_calls, investigation.id
                ).classify(
                    ClassificationEvidence(
                        asserts_failure=result.validation.asserts_failure,
                        validation_reason=result.validation.reason,
                        pytest_exit_code=latest_attempt.execution.evidence.pytest_exit_code,
                        pytest_output_path=latest_attempt.execution.evidence.pytest_output_path,
                        git_diff_path=latest_attempt.execution.evidence.git_diff_path,
                    )
                )
                investigations.update(
                    investigation,
                    classification=classification,
                    classification_model=("deterministic-validator" if result.validation.asserts_failure else CLASSIFICATION_MODEL),
                    classification_completed_at=datetime.now(timezone.utc),
                )
            except Exception:
                investigations.update(investigation, status=InvestigationStatus.FAILED)
                raise
        print("Investigation Complete")
        print(f"assertsFailure: {'TRUE' if result.validation.asserts_failure else 'FALSE'}")
        print("Reason:")
        print(result.validation.reason)
        print("Classification:")
        print(classification.value)
        for path in result.validation.failing_test_paths:
            print(path)
        return 0
    if args.command == "batch-triage":
        settings = Settings(demo_repository=args.repository) if args.repository else Settings()
        session_factory = create_session_factory(settings.database_url)
        issue_service = GitHubIssueService(GitHubClient(settings.demo_repository, settings.github_token))
        with session_factory() as session:
            investigations = InvestigationRepository(session)
            processed = investigations.processed_issue_numbers
        batch_service = BatchTriageService(
            issue_service,
            processed,
            lambda issue: _process_batch_issue(settings, issue),
        )
        summary = batch_service.run(
            settings.demo_repository, args.count, args.start_page, args.force, progress=lambda message: print(message)
        )
        _print_batch_summary(summary)
        return 0
    return 1


def _runner_context(settings: Settings):
    if settings.investigation_runner == "local":
        return nullcontext(LocalInvestigationRunner())
    manager = SandboxManager(
        workspace_root=settings.sandbox_workspace_dir,
        image_name=settings.sandbox_image,
        dependency_timeout_seconds=settings.dependency_install_timeout_seconds,
        overall_timeout_seconds=settings.investigation_timeout_seconds,
        auth_path=settings.codex_auth_path,
        setup_command=settings.sandbox_setup_command,
    )
    return DockerInvestigationRunner(manager, settings.demo_repository, settings.pytest_timeout_seconds)


def _process_batch_issue(settings: Settings, issue) -> BatchItem:
    """Run the exact single-issue pipeline, one fresh session/sandbox at a time."""
    session_factory = create_session_factory(settings.database_url)
    started = datetime.now(timezone.utc)
    with session_factory() as session:
        llm_calls = LLMCallRepository(session)
        investigations = InvestigationRepository(session)
        investigation = _start_investigation(investigations, issue)
        try:
            extraction = ExtractionService(OpenAIExtractionClient(settings.openai_api_key), llm_calls, investigation.id).extract(issue)
            with _runner_context(settings) as runner:
                result = InvestigationEngine(
                    runner=runner,
                    investigations=investigations,
                    hypotheses=HypothesisRepository(session),
                    artifacts=ArtifactRepository(session),
                    llm_calls=llm_calls,
                    artifacts_root=settings.artifacts_dir,
                    validator=EvidenceValidator(),
                ).investigate(issue, extraction, settings.local_repository_path, investigation)
            latest_attempt = result.attempts[-1]
            classification = ClassificationService(OpenAIClassificationClient(settings.openai_api_key), llm_calls, investigation.id).classify(
                ClassificationEvidence(
                    asserts_failure=result.validation.asserts_failure,
                    validation_reason=result.validation.reason,
                    pytest_exit_code=latest_attempt.execution.evidence.pytest_exit_code,
                    pytest_output_path=latest_attempt.execution.evidence.pytest_output_path,
                    git_diff_path=latest_attempt.execution.evidence.git_diff_path,
                )
            )
            investigations.update(
                investigation,
                classification=classification,
                classification_model=("deterministic-validator" if result.validation.asserts_failure else CLASSIFICATION_MODEL),
                classification_completed_at=datetime.now(timezone.utc),
            )
        except Exception:
            investigations.update(investigation, status=InvestigationStatus.FAILED)
            raise
    duration = (datetime.now(timezone.utc) - started).total_seconds()
    return BatchItem(issue, result.investigation_id, classification, duration, None)


def _start_investigation(investigations: InvestigationRepository, issue) -> Investigation:
    investigation = investigations.create(
        Investigation(
            repository=issue.repository,
            issue_number=issue.issue_number,
            issue_title=issue.title,
            status=InvestigationStatus.PENDING,
        )
    )
    return investigations.update(investigation, status=InvestigationStatus.RUNNING)


def _print_batch_summary(summary) -> None:
    print("\nBatch triage summary")
    print("Issue  Title                                                        Investigation  Verdict              Duration  Cost")
    for item in summary.items:
        title = item.issue.title.replace("\n", " ")[:60]
        verdict = "SKIPPED" if item.skipped else (item.classification.value if item.classification else "OPERATIONAL_FAILURE")
        investigation_id = item.investigation_id or "—"
        duration = "—" if item.duration_seconds is None else f"{item.duration_seconds:.1f}s"
        cost = "—" if item.cost_usd is None else f"${item.cost_usd:.6f}"
        print(f"#{item.issue.issue_number:<5} {title:<60} {investigation_id[:8]:<14} {verdict:<20} {duration:<9} {cost}")
    print("Counts: " + ", ".join(f"{key}={value}" for key, value in summary.counts().items()))
