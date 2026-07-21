from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, event, func
from sqlalchemy.orm import Mapped, mapped_column

from triage.domain.enums import AssessmentConfidence, AssessmentJudgment, BudgetStatus, Classification, CommentStatus, ConsensusState, CorpusConsentStatus, EligibilityState, InvestigationStatus, JobSource, PostingApprovalStatus, ReviewActivityType, ReviewerCohort, WebhookJobStatus
from triage.persistence.database import Base


def _id() -> str:
    return str(uuid4())


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    repository: Mapped[str] = mapped_column(String(255), nullable=False)
    issue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_runner: Mapped[str] = mapped_column(String(32), nullable=False, default="pytest")
    status: Mapped[InvestigationStatus] = mapped_column(
        Enum(InvestigationStatus, native_enum=False), nullable=False, default=InvestigationStatus.PENDING
    )
    classification: Mapped[Classification | None] = mapped_column(
        Enum(Classification, native_enum=False), nullable=True
    )
    classification_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    classification_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    asserts_failure: Mapped[bool] = mapped_column(nullable=False, default=False)
    validation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    tracked_openai_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    reserved_openai_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=Decimal("0"))
    codex_invocation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    codex_wall_seconds: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    codex_wall_cap_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    budget_status: Mapped[BudgetStatus] = mapped_column(Enum(BudgetStatus, native_enum=False), nullable=False, default=BudgetStatus.AVAILABLE)
    budget_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_packet_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    review_packet_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Hypothesis(Base):
    __tablename__ = "hypotheses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    revision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewPacket(Base):
    """An append-only reviewer evidence snapshot; never update packet fields."""
    __tablename__ = "review_packets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    integrity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReviewAssessment(Base):
    """Append-only independent labels for one immutable review packet."""
    __tablename__ = "review_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    review_packet_id: Mapped[str] = mapped_column(ForeignKey("review_packets.id"), nullable=False, index=True)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"), nullable=False, index=True)
    packet_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    packet_version: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewer_external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewer_cohort: Mapped[ReviewerCohort] = mapped_column(Enum(ReviewerCohort, native_enum=False), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    extraction_aligned: Mapped[AssessmentJudgment] = mapped_column(Enum(AssessmentJudgment, native_enum=False), nullable=False)
    test_aligned: Mapped[AssessmentJudgment] = mapped_column(Enum(AssessmentJudgment, native_enum=False), nullable=False)
    failure_supports_signal: Mapped[AssessmentJudgment] = mapped_column(Enum(AssessmentJudgment, native_enum=False), nullable=False)
    public_comment_appropriate: Mapped[AssessmentJudgment] = mapped_column(Enum(AssessmentJudgment, native_enum=False), nullable=False)
    confidence: Mapped[AssessmentConfidence] = mapped_column(Enum(AssessmentConfidence, native_enum=False), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason_tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    supersedes_assessment_id: Mapped[str | None] = mapped_column(ForeignKey("review_assessments.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReviewAssessmentAudit(Base):
    __tablename__ = "review_assessment_audit"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("review_assessments.id"), nullable=False, unique=True)
    reviewer_external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    packet_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReviewConsensusSnapshot(Base):
    """Append-only, reproducible result of the versioned consensus algorithm."""
    __tablename__ = "review_consensus_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    review_packet_id: Mapped[str] = mapped_column(ForeignKey("review_packets.id"), nullable=False, index=True)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"), nullable=False, index=True)
    packet_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    packet_version: Mapped[int] = mapped_column(Integer, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[ConsensusState] = mapped_column(Enum(ConsensusState, native_enum=False), nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PostingApproval(Base):
    __tablename__ = "posting_approvals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"), nullable=False, index=True)
    review_packet_id: Mapped[str] = mapped_column(ForeignKey("review_packets.id"), nullable=False, index=True)
    packet_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    packet_version: Mapped[int] = mapped_column(Integer, nullable=False)
    consensus_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("review_consensus_snapshots.id"), nullable=True)
    consensus_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    consensus_algorithm_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment_body_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    classification: Mapped[Classification] = mapped_column(Enum(Classification, native_enum=False), nullable=False)
    comment_type: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewer_external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewer_cohort: Mapped[ReviewerCohort] = mapped_column(Enum(ReviewerCohort, native_enum=False), nullable=False)
    reviewer_role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[PostingApprovalStatus] = mapped_column(Enum(PostingApprovalStatus, native_enum=False), nullable=False, default=PostingApprovalStatus.ACTIVE)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PostingApprovalEvent(Base):
    __tablename__ = "posting_approval_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    approval_id: Mapped[str] = mapped_column(ForeignKey("posting_approvals.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReviewActivity(Base):
    __tablename__ = "review_activities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    review_packet_id: Mapped[str | None] = mapped_column(ForeignKey("review_packets.id"), nullable=True, index=True)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"), nullable=False, index=True)
    reviewer_external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewer_cohort: Mapped[ReviewerCohort] = mapped_column(Enum(ReviewerCohort, native_enum=False), nullable=False)
    session_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[ReviewActivityType] = mapped_column(Enum(ReviewActivityType, native_enum=False), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReviewWorkSession(Base):
    __tablename__ = "review_work_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    review_packet_id: Mapped[str] = mapped_column(ForeignKey("review_packets.id"), nullable=False, index=True)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"), nullable=False, index=True)
    reviewer_external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewer_cohort: Mapped[ReviewerCohort] = mapped_column(Enum(ReviewerCohort, native_enum=False), nullable=False)
    session_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated: Mapped[bool] = mapped_column(nullable=False, default=False)


class PilotWeeklyReport(Base):
    __tablename__ = "pilot_weekly_reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    repository: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    report_json: Mapped[str] = mapped_column(Text, nullable=False)
    report_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CorpusConsent(Base):
    __tablename__ = "corpus_consents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    repository: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="EVALUATION_ONLY")
    status: Mapped[CorpusConsentStatus] = mapped_column(Enum(CorpusConsentStatus, native_enum=False), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(32), nullable=False)
    operator_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    allowed_data_classes_json: Mapped[str] = mapped_column(Text, nullable=False)
    retention_policy_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    audit_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CorpusExport(Base):
    __tablename__ = "corpus_exports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    repositories_json: Mapped[str] = mapped_column(Text, nullable=False)
    consent_provenance_json: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    source_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    operator_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AutomationEligibilityPolicy(Base):
    __tablename__ = "automation_eligibility_policies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    cohort_key: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    repositories_json: Mapped[str] = mapped_column(Text, nullable=False)
    predicates_json: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    operator_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EligibilityReport(Base):
    __tablename__ = "eligibility_reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    policy_id: Mapped[str] = mapped_column(ForeignKey("automation_eligibility_policies.id"), nullable=False, index=True)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[EligibilityState] = mapped_column(Enum(EligibilityState, native_enum=False), nullable=False)
    report_json: Mapped[str] = mapped_column(Text, nullable=False)
    report_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    operator_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@event.listens_for(ReviewPacket, "before_update")
def _prevent_review_packet_mutation(mapper, connection, target) -> None:
    raise ValueError("Review packets are immutable; issue a new version instead")


@event.listens_for(ReviewPacket, "before_delete")
def _prevent_review_packet_deletion(mapper, connection, target) -> None:
    raise ValueError("Review packets are immutable historical records")


@event.listens_for(ReviewAssessment, "before_update")
@event.listens_for(ReviewAssessment, "before_delete")
def _prevent_review_assessment_mutation(mapper, connection, target) -> None:
    raise ValueError("Review assessments are append-only; submit a superseding assessment instead")


@event.listens_for(ReviewConsensusSnapshot, "before_update")
@event.listens_for(ReviewConsensusSnapshot, "before_delete")
def _prevent_consensus_snapshot_mutation(mapper, connection, target) -> None:
    raise ValueError("Consensus snapshots are append-only historical records")


@event.listens_for(PostingApproval, "before_update")
@event.listens_for(PostingApproval, "before_delete")
@event.listens_for(PostingApprovalEvent, "before_update")
@event.listens_for(PostingApprovalEvent, "before_delete")
def _prevent_posting_approval_mutation(mapper, connection, target) -> None:
    raise ValueError("Posting approvals and their audit events are append-only")


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    investigation_id: Mapped[str | None] = mapped_column(ForeignKey("investigations.id"), nullable=True)
    attempt_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    pricing_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WebhookJob(Base):
    """One accepted GitHub delivery; delivery_id is the durable idempotency key."""
    __tablename__ = "webhook_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    delivery_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    source: Mapped[JobSource] = mapped_column(Enum(JobSource, native_enum=False), nullable=False, default=JobSource.WEBHOOK)
    repository: Mapped[str] = mapped_column(String(255), nullable=False)
    issue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[WebhookJobStatus] = mapped_column(Enum(WebhookJobStatus, native_enum=False), nullable=False, default=WebhookJobStatus.QUEUED)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    lease_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_eligible_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    investigation_id: Mapped[str | None] = mapped_column(ForeignKey("investigations.id"), nullable=True)
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment_status: Mapped[CommentStatus] = mapped_column(Enum(CommentStatus, native_enum=False), nullable=False, default=CommentStatus.PENDING)
    comment_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_comment_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_comment_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_comment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    posting_approval_id: Mapped[str | None] = mapped_column(ForeignKey("posting_approvals.id"), nullable=True)
    posting_approval_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    budget_status: Mapped[BudgetStatus] = mapped_column(Enum(BudgetStatus, native_enum=False), nullable=False, default=BudgetStatus.AVAILABLE)
    budget_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_stage: Mapped[str | None] = mapped_column(String(48), nullable=True)
    progress_detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SimilarityDocument(Base):
    __tablename__ = "similarity_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"), unique=True, nullable=False)
    repository: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    document_version: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_text: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embedding_vector: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_status: Mapped[str] = mapped_column(String(32), nullable=False, default="EXACT_ONLY")
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DuplicateCandidate(Base):
    __tablename__ = "duplicate_candidates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    source_investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"), nullable=False)
    candidate_investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"), nullable=False)
    repository: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    similarity_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    scoring_version: Mapped[str] = mapped_column(String(32), nullable=False)
    matched_signals: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="SUGGESTED")
    stale: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
