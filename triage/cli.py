import argparse
import json
from contextlib import nullcontext
from collections.abc import Sequence
from datetime import datetime, timezone
from datetime import date
from pathlib import Path

from triage.classification.client import MODEL as CLASSIFICATION_MODEL, OpenAIClassificationClient
from triage.classification.models import ClassificationEvidence
from triage.classification.service import ClassificationService
from triage.batch import BatchItem, BatchTriageService, DEFAULT_BATCH_SIZE, DEFAULT_MAX_SCAN_PAGES, MAX_BATCH_SIZE
from triage.config.settings import Settings
from triage.domain.enums import InvestigationStatus
from triage.extraction.client import OpenAIExtractionClient
from triage.extraction.service import ExtractionService
from triage.github.client import GitHubClient, GitHubRateLimitError
from triage.github.service import GitHubIssueService
from triage.investigation.engine import InvestigationEngine
from triage.investigation.runner import LocalInvestigationRunner
from triage.persistence.database import create_session_factory
from triage.persistence.models import Investigation
from triage.persistence.repositories import ArtifactRepository, HypothesisRepository, InvestigationRepository, LLMCallRepository, WebhookJobRepository
from triage.sandbox.manager import EnvironmentSetupFailure, SandboxManager
from triage.sandbox.runner import DockerInvestigationRunner
from triage.validation.validator import EvidenceValidator
from triage.budget import BudgetService
from triage.preflight import PreflightError, format_result, require_safe_to_start, run_preflight


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="triage")
    subparsers = parser.add_subparsers(dest="command", required=True)
    fetch = subparsers.add_parser("fetch", help="Fetch and normalize a GitHub issue")
    fetch.add_argument("issue_number", type=int)
    extract = subparsers.add_parser("extract", help="Extract a reproduction specification from a GitHub issue")
    extract.add_argument("issue_number", type=int)
    investigate = subparsers.add_parser("investigate", help="Run bounded Codex investigation in Docker")
    investigate.add_argument("issue_number", type=int)
    preflight = subparsers.add_parser("preflight", help="Read-only live-investigation configuration diagnostic")
    preflight.add_argument("--repository", required=True, help="Public repository in owner/repository form")
    batch = subparsers.add_parser("batch-triage", help="Sequentially investigate newest open GitHub issues")
    batch.add_argument("--repository", default=None, help="Repository to triage (defaults to DEMO_REPOSITORY)")
    batch.add_argument("--count", type=int, default=DEFAULT_BATCH_SIZE, help=f"Issues to select (1-{MAX_BATCH_SIZE})")
    batch.add_argument("--start-page", type=int, default=1, help="GitHub open-issues page to start from")
    batch.add_argument(
        "--max-scan-pages", type=int, default=DEFAULT_MAX_SCAN_PAGES,
        help=f"Maximum GitHub issue pages to scan while finding new issues (default: {DEFAULT_MAX_SCAN_PAGES})",
    )
    batch.add_argument("--force", action="store_true", help="Reprocess issues that already have a completed/failed investigation")
    batch.add_argument("--enqueue", action="store_true", help="Enqueue selected issues instead of running them inline")
    batch.add_argument("--wait", action="store_true", help="When enqueueing, drain eligible jobs after selection")
    worker = subparsers.add_parser("webhook-worker", help="Process one queued GitHub webhook job at a time")
    worker.add_argument("--once", action="store_true", help="Process at most one job (the current worker mode)")
    durable_worker = subparsers.add_parser("worker", help="Run durable investigation jobs")
    durable_worker.add_argument("--once", action="store_true", help="Claim and process one job")
    durable_worker.add_argument("--concurrency", type=int, default=None, help="Global parallel job limit")
    durable_worker.add_argument("--drain", action="store_true", help="Process eligible jobs until the queue is empty")
    replay = subparsers.add_parser("replay", help="Create a separate replay plan from a reproducibility manifest")
    replay.add_argument("manifest", type=str)
    report = subparsers.add_parser("pilot-weekly-report", help="Generate aggregate-only local pilot weekly report")
    report.add_argument("--repository", required=True)
    report.add_argument("--week-start", required=True, help="ISO Monday date (UTC)")
    report.add_argument("--csv", action="store_true")
    corpus = subparsers.add_parser("export-semantic-corpus", help="Export consented evaluation-only semantic corpus")
    corpus.add_argument("--repository", action="append", required=True)
    corpus.add_argument("--output", required=True)
    corpus.add_argument("--operator", required=True)
    corpus.add_argument("--confirm-evaluation-only", action="store_true")
    eligibility = subparsers.add_parser("evaluate-automation-eligibility", help="Generate measurement-only eligibility report")
    eligibility.add_argument("--policy", required=True)
    eligibility.add_argument("--operator", required=True)
    eligibility.add_argument("--confirm-measurement-only", action="store_true")
    compare = subparsers.add_parser("compare-investigation-providers", help="Create consented bounded provider comparison plan")
    compare.add_argument("--repository", required=True); compare.add_argument("--baseline", default="codex"); compare.add_argument("--candidate", required=True); compare.add_argument("--max-examples", type=int, required=True); compare.add_argument("--max-wall-seconds", type=int, required=True); compare.add_argument("--operator", required=True); compare.add_argument("--output", required=True); compare.add_argument("--confirm-evaluation-only", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "pilot-weekly-report":
        from triage.pilot_reports import PilotReportService, weekly_window
        settings = Settings(); start, end = weekly_window(date.fromisoformat(args.week_start))
        with create_session_factory(settings.database_url)() as session:
            report = PilotReportService(session).generate(args.repository, start, end)
            print(PilotReportService(session).csv(report) if args.csv else report.report_json)
        return 0
    if args.command == "export-semantic-corpus":
        if not args.confirm_evaluation_only:
            parser.error("--confirm-evaluation-only is required")
        from triage.semantic_corpus import SemanticCorpusService
        with create_session_factory(Settings().database_url)() as session:
            result = SemanticCorpusService(session).export(args.repository, Path(args.output), args.operator)
        print(result.manifest_hash)
        return 0
    if args.command == "evaluate-automation-eligibility":
        if not args.confirm_measurement_only: parser.error("--confirm-measurement-only is required")
        from triage.automation_eligibility import EligibilityService
        with create_session_factory(Settings().database_url)() as session:
            report = EligibilityService(session).evaluate(args.policy, args.operator)
        print(report.report_hash)
        return 0
    if args.command == "compare-investigation-providers":
        if not args.confirm_evaluation_only: parser.error("--confirm-evaluation-only is required")
        from triage.provider_comparison import ProviderComparisonService
        with create_session_factory(Settings().database_url)() as session:
            plan=ProviderComparisonService(session).plan(args.repository,args.baseline,args.candidate,args.max_examples,args.max_wall_seconds,args.operator,Path(args.output))
        print(plan["manifest_hash"]); return 0

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
    if args.command == "preflight":
        try:
            result = run_preflight(Settings(), args.repository)
            print(format_result(result))
            return 0 if result.safe_to_start else 2
        except PreflightError as error:
            print(f"Preflight failed: {error}")
            return 2
    if args.command == "investigate":
        settings = Settings()
        try:
            require_safe_to_start(settings, settings.demo_repository)
        except PreflightError as error:
            print(f"Preflight blocked live investigation: {error}")
            return 2
        issue = GitHubIssueService(
            GitHubClient(settings.demo_repository, settings.github_token)
        ).fetch_issue(args.issue_number)
        session_factory = create_session_factory(settings.database_url)
        with session_factory() as session:
            llm_calls = LLMCallRepository(session)
            investigations = InvestigationRepository(session)
            investigation = _start_investigation(investigations, issue, settings.test_runner)
            try:
                budget = BudgetService(session, settings)
                extraction = ExtractionService(
                    OpenAIExtractionClient(settings.openai_api_key), llm_calls, investigation.id, budget
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
                        confirmation_runs=settings.confirmation_runs,
                        budget=budget,
                    ).investigate(issue, extraction, settings.local_repository_path, investigation)
                latest_attempt = result.attempts[-1] if result.attempts else None
                if latest_attempt is None:
                    raise RuntimeError("Investigation produced no execution evidence for classification")
                classification = ClassificationService(
                    OpenAIClassificationClient(settings.openai_api_key), llm_calls, investigation.id, budget
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
                # Issuance is deliberately best-effort and cannot affect the
                # deterministic validation, classification, or CLI outcome.
                from triage.review_packets import ReviewPacketService
                ReviewPacketService(session).issue_safely(investigation.id)
            except Exception:
                investigations.update(investigation, status=InvestigationStatus.FAILED)
                raise
        print("Investigation Complete")
        print(f"assertsFailure: {'TRUE' if result.validation.asserts_failure else 'FALSE'}")
        print("Reason:")
        print(result.validation.reason)
        print("Classification:")
        print(_classification_label(classification))
        for path in result.validation.failing_test_paths:
            print(path)
        return 0
    if args.command == "batch-triage":
        settings = Settings(demo_repository=args.repository) if args.repository else Settings()
        try:
            require_safe_to_start(settings, settings.demo_repository)
        except PreflightError as error:
            print(f"Preflight blocked batch triage: {error}")
            return 2
        session_factory = create_session_factory(settings.database_url)
        issue_service = GitHubIssueService(GitHubClient(settings.demo_repository, settings.github_token))
        with session_factory() as session:
            investigations = InvestigationRepository(session)
            processed = investigations.processed_issue_numbers
        def queue_batch_issue(issue):
            with session_factory() as session:
                job = WebhookJobRepository(session).enqueue_batch(
                    issue.repository, issue.issue_number, max_attempts=settings.worker_max_attempts
                )
            return BatchItem(issue, job.investigation_id, None, None, None, job_status=job.status.value)
        batch_service = BatchTriageService(
            issue_service,
            processed,
            queue_batch_issue if args.enqueue else lambda issue: _process_batch_issue(settings, issue),
        )
        try:
            summary = batch_service.run(
                settings.demo_repository,
                args.count,
                args.start_page,
                args.force,
                progress=lambda message: print(message),
                max_scan_pages=args.max_scan_pages,
            )
        except GitHubRateLimitError as error:
            print(f"Unable to select batch candidates: {error}")
            return 2
        _print_batch_summary(summary)
        if args.enqueue and args.wait:
            from triage.webhook.worker import WebhookWorker
            completed = WebhookWorker(settings, session_factory).run(drain=True)
            print(f"Queue drain processed {completed} job(s).")
        return 0
    if args.command in {"webhook-worker", "worker"}:
        from triage.webhook.worker import WebhookWorker
        settings = Settings()
        queue_worker = WebhookWorker(settings, create_session_factory(settings.database_url))
        if args.command == "webhook-worker" or args.once:
            worked = queue_worker.run_once()
            print("Processed one job." if worked else "No queued jobs.")
        else:
            count = queue_worker.run(args.concurrency, args.drain)
            print(f"Processed {count} job(s).")
        return 0
    if args.command == "replay":
        from triage.replay import create_replay_plan
        settings = Settings()
        try:
            plan = create_replay_plan(Path(args.manifest), settings.artifacts_dir)
        except ValueError as error:
            print(str(error))
            return 2
        print(f"Replay plan created: {plan}")
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
        test_runner=settings.test_runner,
        network_policy=settings.test_network_policy,
        agent_network_policy=settings.agent_network_policy,
        confirmation_runs=settings.confirmation_runs,
    )
    if settings.investigation_agent_provider == "claude_code":
        from triage.sandbox.claude_code import ClaudeCodeInvestigationAgentProvider
        runner = ClaudeCodeInvestigationAgentProvider(manager, settings.demo_repository, settings.pytest_timeout_seconds, settings.claude_code_command or "", settings.claude_code_model)
        runner.validate()
        return runner
    return DockerInvestigationRunner(manager, settings.demo_repository, settings.pytest_timeout_seconds)


def _process_batch_issue(settings: Settings, issue) -> BatchItem:
    """Run the exact single-issue pipeline, one fresh session/sandbox at a time."""
    session_factory = create_session_factory(settings.database_url)
    started = datetime.now(timezone.utc)
    with session_factory() as session:
        llm_calls = LLMCallRepository(session)
        investigations = InvestigationRepository(session)
        investigation = _start_investigation(investigations, issue, settings.test_runner)
        try:
            budget = BudgetService(session, settings)
            extraction = ExtractionService(OpenAIExtractionClient(settings.openai_api_key), llm_calls, investigation.id, budget).extract(issue)
            with _runner_context(settings) as runner:
                result = InvestigationEngine(
                    runner=runner,
                    investigations=investigations,
                    hypotheses=HypothesisRepository(session),
                    artifacts=ArtifactRepository(session),
                    llm_calls=llm_calls,
                    artifacts_root=settings.artifacts_dir,
                    validator=EvidenceValidator(),
                    confirmation_runs=settings.confirmation_runs,
                    budget=budget,
                ).investigate(issue, extraction, settings.local_repository_path, investigation)
            latest_attempt = result.attempts[-1]
            classification = ClassificationService(OpenAIClassificationClient(settings.openai_api_key), llm_calls, investigation.id, budget).classify(
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
        except EnvironmentSetupFailure as error:
            investigations.update(investigation, status=InvestigationStatus.FAILED, asserts_failure=False, validation_reason=str(error))
            return BatchItem(issue, investigation.id, None, (datetime.now(timezone.utc) - started).total_seconds(), None, error=str(error))
        except Exception:
            investigations.update(investigation, status=InvestigationStatus.FAILED)
            raise
    duration = (datetime.now(timezone.utc) - started).total_seconds()
    return BatchItem(issue, result.investigation_id, classification, duration, llm_calls.tracked_cost_usd(investigation.id))


def _start_investigation(investigations: InvestigationRepository, issue, test_runner: str = "pytest") -> Investigation:
    investigation = investigations.create(
        Investigation(
            repository=issue.repository,
            issue_number=issue.issue_number,
            issue_title=issue.title,
            test_runner=test_runner,
            status=InvestigationStatus.PENDING,
        )
    )
    return investigations.update(investigation, status=InvestigationStatus.RUNNING)


def _print_batch_summary(summary) -> None:
    print("\nBatch triage summary")
    print("Issue  Title                                                        Investigation  Verdict              Duration  Cost")
    for item in summary.items:
        title = item.issue.title.replace("\n", " ")[:60]
        verdict = "SKIPPED" if item.skipped else (item.job_status or (_classification_label(item.classification) if item.classification else "OPERATIONAL_FAILURE"))
        investigation_id = item.investigation_id or "—"
        duration = "—" if item.duration_seconds is None else f"{item.duration_seconds:.1f}s"
        cost = "—" if item.cost_usd is None else f"${item.cost_usd:.6f}"
        print(f"#{item.issue.issue_number:<5} {title:<60} {investigation_id[:8]:<14} {verdict:<20} {duration:<9} {cost}")
    print("Counts: " + ", ".join(f"{key}={value}" for key, value in summary.counts().items()))
    print(
        f"Selection: requested {summary.requested_count} new issues; selected {summary.selected_count}; "
        f"skipped {summary.skipped_count} already processed; scanned {summary.pages_scanned} pages; {summary.selection_end}."
    )
    if summary.selected_count < summary.requested_count:
        message = (
            f"Requested {summary.requested_count} new issues; found {summary.selected_count} eligible unprocessed issues "
            f"after scanning {summary.pages_scanned} pages ({summary.selection_end})."
        )
        if summary.selection_end == "scan-page limit reached":
            message += " Try --start-page, a smaller count, or GITHUB_TOKEN."
        print(message)


def _classification_label(classification) -> str:
    if classification.value == "BEHAVIOR_GAP_CONFIRMED":
        return "Behavior gap confirmed"
    return classification.value
