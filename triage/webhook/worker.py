"""Bounded durable queue worker; never used from the HTTP handler."""

import json
import re
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path
from typing import Callable

from sqlalchemy import select

from triage.config.settings import Settings
from triage.domain.enums import CommentStatus, WebhookJobStatus
from triage.github.client import GitHubClient
from triage.github.service import GitHubIssueService
from triage.persistence.models import Artifact, Investigation, WebhookJob
from triage.persistence.repositories import WebhookJobRepository
from triage.webhook.comments import MARKER_PREFIX, render_comment
from triage.budget import BudgetExceeded
from triage.domain.enums import BudgetStatus


class WebhookWorker:
    def __init__(self, settings: Settings, session_factory, process_issue: Callable | None = None, github_client_factory=GitHubClient):
        self.settings = settings
        self.session_factory = session_factory
        self.process_issue = process_issue or self._default_process_issue
        self.github_client_factory = github_client_factory

    def run_once(self, owner: str = "worker") -> bool:
        with self.session_factory() as session:
            jobs = WebhookJobRepository(session)
            job = jobs.claim_next(owner, self.settings.worker_lease_seconds, self.settings.worker_per_repository_concurrency)
            if job is None:
                return False
            job_id = job.id
        try:
            investigation_id = self.process_issue(job.repository, job.issue_number)
            with self.session_factory() as session:
                job = session.get(WebhookJob, job_id)
                assert job is not None
                jobs = WebhookJobRepository(session)
                jobs.update(job, investigation_id=investigation_id)
                # Advisory-only, post-investigation analysis. Failures here
                # never affect classification, job success, or commenting.
                try:
                    from triage.similarity import DuplicateSimilarityService
                    DuplicateSimilarityService(session, self.settings).analyze(investigation_id)
                except Exception:
                    pass
                # A packet must exist before comment gating can bind a human
                # approval to immutable evidence. Issuance remains advisory.
                from triage.review_packets import ReviewPacketService
                ReviewPacketService(session).issue_safely(investigation_id)
                self._decide_comment(session, job)
                jobs.finish(job, WebhookJobStatus.SUCCEEDED)
        except Exception as error:
            with self.session_factory() as session:
                job = session.get(WebhookJob, job_id)
                if job is not None:
                    safe_error = _safe_error(error)
                    jobs = WebhookJobRepository(session)
                    if isinstance(error, BudgetExceeded):
                        jobs.finish(job, WebhookJobStatus.FAILED, error_reason=safe_error, budget_status=BudgetStatus.EXCEEDED, budget_reason=safe_error, comment_status=CommentStatus.SKIPPED, comment_reason="Budget exhausted; no public comment")
                        return True
                    if _is_transient(error) and job.attempt_count < job.max_attempts:
                        delay = min(300, 2 ** job.attempt_count)
                        from datetime import timedelta
                        jobs.finish(job, WebhookJobStatus.RETRY_SCHEDULED, error_reason=safe_error, next_eligible_at=datetime.now(timezone.utc) + timedelta(seconds=delay), comment_status=CommentStatus.SKIPPED, comment_reason="Transient operational failure; retry scheduled")
                    else:
                        jobs.finish(job, WebhookJobStatus.DEAD_LETTER if job.attempt_count >= job.max_attempts else WebhookJobStatus.FAILED, error_reason=safe_error, comment_status=CommentStatus.SKIPPED, comment_reason="Operational failure")
        return True

    def run(self, concurrency: int | None = None, drain: bool = False) -> int:
        """Claim work up to the configured global bound; each job owns a thread/session."""
        limit = concurrency or self.settings.worker_concurrency
        if limit < 1:
            raise ValueError("Worker concurrency must be at least one")
        processed = 0
        with ThreadPoolExecutor(max_workers=limit) as executor:
            futures = set()
            sequence = 0
            while True:
                while len(futures) < limit:
                    sequence += 1
                    future = executor.submit(self.run_once, f"worker-{sequence}")
                    # A false result means this slot found no eligible work.
                    futures.add(future)
                    if not drain:
                        break
                done, futures = wait(futures, return_when="FIRST_COMPLETED")
                results = [future.result() for future in done]
                processed += sum(results)
                if not drain or not any(results):
                    break
        return processed

    def _default_process_issue(self, repository: str, issue_number: int) -> str:
        # Import lazily to keep API startup free of Docker/Codex setup.
        from triage.cli import _process_batch_issue
        issue = GitHubIssueService(self.github_client_factory(repository, self.settings.github_token)).fetch_issue(issue_number)
        item = _process_batch_issue(self.settings.model_copy(update={"demo_repository": repository}), issue)
        return item.investigation_id

    def _decide_comment(self, session, job: WebhookJob) -> None:
        investigation = session.get(Investigation, job.investigation_id)
        if investigation is None:
            raise RuntimeError("Worker did not persist an investigation")
        extraction = self._extraction(session, investigation.id)
        body = render_comment(investigation, job.delivery_id, extraction, self._diff_excerpt(session, investigation.id))
        jobs = WebhookJobRepository(session)
        if body is None:
            jobs.update(job, comment_status=CommentStatus.SKIPPED, comment_reason="Verdict has no public-comment policy")
            return
        if not self.settings.github_auto_post_enabled:
            jobs.update(job, comment_status=CommentStatus.SKIPPED, proposed_comment_body=body, comment_reason="Global auto-post is disabled")
            return
        if job.repository.lower() not in self.settings.auto_post_allowlist():
            jobs.update(job, comment_status=CommentStatus.SKIPPED, proposed_comment_body=body, comment_reason="Repository is not approved for auto-post")
            return
        if self.settings.github_auto_post_dry_run:
            jobs.update(job, comment_status=CommentStatus.PROPOSED, proposed_comment_body=body, comment_reason="Dry-run enabled; not posted")
            return
        from triage.posting_approvals import PostingApprovalService
        approvals = PostingApprovalService(session)
        approval, approval_status = approvals.valid_approval(investigation.id, body)
        if approval is None:
            status = CommentStatus.CONSENSUS_REQUIRED if approval_status == "CONSENSUS_REQUIRED" else CommentStatus.APPROVAL_EXPIRED if approval_status == "APPROVAL_EXPIRED" else CommentStatus.REVIEW_REQUIRED
            jobs.update(job, comment_status=status, proposed_comment_body=body, comment_reason=f"{approval_status}: human approval of this exact review packet and comment preview is required")
            return
        # A completed job is never re-claimed; retain an additional guard for manual retries.
        if job.github_comment_id:
            return
        try:
            # Revalidate immediately before the only outbound GitHub action.
            approval, approval_status = approvals.valid_approval(investigation.id, body)
            if approval is None:
                jobs.update(job, comment_status=CommentStatus.REVIEW_REQUIRED, proposed_comment_body=body, comment_reason=f"{approval_status}: approval invalidated before posting")
                return
            client = self.github_client_factory(job.repository, self.settings.github_token)
            marker = f"{MARKER_PREFIX}{job.delivery_id} -->"
            existing = next((item for item in client.fetch_comments(job.issue_number) if marker in str(item.get("body", ""))), None)
            if existing is not None:
                approvals.consume(approval)
                jobs.update(job, comment_status=CommentStatus.POSTED, posted_comment_body=body, github_comment_id=str(existing.get("id")), posting_approval_id=approval.id, posting_approval_hash=approval.approval_hash, comment_reason="Existing application comment detected")
                return
            response = client.create_issue_comment(job.issue_number, body)
            approvals.consume(approval)
            jobs.update(job, comment_status=CommentStatus.POSTED, posted_comment_body=body, github_comment_id=str(response.get("id")), posting_approval_id=approval.id, posting_approval_hash=approval.approval_hash, comment_reason=None)
        except Exception:
            jobs.update(job, comment_status=CommentStatus.FAILED, proposed_comment_body=body, comment_reason="GitHub comment API failed")

    @staticmethod
    def _extraction(session, investigation_id: str) -> dict | None:
        artifact = session.scalar(select(Artifact).where(Artifact.investigation_id == investigation_id, Artifact.kind == "extraction_json"))
        if artifact is None:
            return None
        try:
            return json.loads(Path(artifact.path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _diff_excerpt(session, investigation_id: str) -> str | None:
        artifact = session.scalar(select(Artifact).where(Artifact.investigation_id == investigation_id, Artifact.kind == "git_diff").order_by(Artifact.created_at.desc()))
        if artifact is None:
            return None
        try:
            return Path(artifact.path).read_text(encoding="utf-8", errors="replace")[:900]
        except OSError:
            return None


def _safe_error(error: Exception) -> str:
    value = str(error).replace("\x00", "")[:1000]
    return re.sub(r"(?i)(authorization|token|secret|password)\s*[:=]\s*\S+", r"\1: [redacted]", value)


def _is_transient(error: Exception) -> bool:
    value = str(error).lower()
    return any(token in value for token in ("timeout", "temporar", "network", "connection", "docker", "rate limit", "provider"))
