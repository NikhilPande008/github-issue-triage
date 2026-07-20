import argparse
import json
from contextlib import nullcontext
from collections.abc import Sequence
from datetime import datetime, timezone

from triage.classification.client import MODEL as CLASSIFICATION_MODEL, OpenAIClassificationClient
from triage.classification.models import ClassificationEvidence
from triage.classification.service import ClassificationService
from triage.config.settings import Settings
from triage.extraction.client import OpenAIExtractionClient
from triage.extraction.service import ExtractionService
from triage.github.client import GitHubClient
from triage.github.service import GitHubIssueService
from triage.investigation.engine import InvestigationEngine
from triage.investigation.runner import LocalInvestigationRunner
from triage.persistence.database import create_session_factory
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
            extraction = ExtractionService(
                OpenAIExtractionClient(settings.openai_api_key), llm_calls
            ).extract(issue)
            with _runner_context(settings) as runner:
                result = InvestigationEngine(
                    runner=runner,
                    investigations=InvestigationRepository(session),
                    hypotheses=HypothesisRepository(session),
                    artifacts=ArtifactRepository(session),
                    llm_calls=llm_calls,
                    artifacts_root=settings.artifacts_dir,
                    validator=EvidenceValidator(),
                ).investigate(issue, extraction, settings.local_repository_path)
            latest_attempt = result.attempts[-1] if result.attempts else None
            if latest_attempt is None:
                raise RuntimeError("Investigation produced no execution evidence for classification")
            classification = ClassificationService(
                OpenAIClassificationClient(settings.openai_api_key), llm_calls
            ).classify(
                ClassificationEvidence(
                    asserts_failure=result.validation.asserts_failure,
                    validation_reason=result.validation.reason,
                    pytest_exit_code=latest_attempt.execution.evidence.pytest_exit_code,
                    pytest_output_path=latest_attempt.execution.evidence.pytest_output_path,
                    git_diff_path=latest_attempt.execution.evidence.git_diff_path,
                )
            )
            investigation = InvestigationRepository(session).get(result.investigation_id)
            if investigation is None:
                raise RuntimeError("Investigation record was not found for classification persistence")
            InvestigationRepository(session).update(
                investigation,
                classification=classification,
                classification_model=("deterministic-validator" if result.validation.asserts_failure else CLASSIFICATION_MODEL),
                classification_completed_at=datetime.now(timezone.utc),
            )
        print("Investigation Complete")
        print(f"assertsFailure: {'TRUE' if result.validation.asserts_failure else 'FALSE'}")
        print("Reason:")
        print(result.validation.reason)
        print("Classification:")
        print(classification.value)
        for path in result.validation.failing_test_paths:
            print(path)
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
    )
    return DockerInvestigationRunner(manager, settings.demo_repository, settings.pytest_timeout_seconds)
