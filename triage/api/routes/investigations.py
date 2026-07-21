from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from triage.config.settings import Settings
from triage.domain.enums import Classification
from triage.llm.pricing import OPENAI_PROVIDER
from triage.persistence.database import create_session_factory
from triage.persistence.models import Artifact, Hypothesis, Investigation, LLMCall

router = APIRouter(prefix="/investigations", tags=["investigations"])


def get_session():
    factory = create_session_factory(Settings().database_url)
    with factory() as session:
        yield session


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _duration_seconds(investigation: Investigation) -> float | None:
    if investigation.created_at is None:
        return None
    end = investigation.classification_completed_at or investigation.updated_at
    if end is None:
        return None
    return max(0.0, (end - investigation.created_at).total_seconds())


def _tracked_llm_metrics(calls: list[LLMCall]) -> dict[str, object]:
    """Aggregate only linked, priced OpenAI API calls; Codex is intentionally excluded."""
    tracked_calls = [call for call in calls if call.provider == OPENAI_PROVIDER]
    caveat = "Tracked LLM API cost and latency include linked OpenAI API calls only; Codex usage is excluded because exact Codex billing data is unavailable."
    if not tracked_calls:
        return {
            "tracked_llm_api_cost_usd": None,
            "tracked_llm_api_latency_ms": None,
            "tracked_llm_api_input_tokens": None,
            "tracked_llm_api_cached_input_tokens": None,
            "tracked_llm_api_output_tokens": None,
            "tracked_llm_api_cost_status": "unavailable",
            "tracked_llm_api_latency_status": "unavailable",
            "tracked_llm_api_explanation": "No tracked LLM API calls are linked to this investigation. " + caveat,
        }
    cost_available = all(call.cost_usd is not None for call in tracked_calls)
    cost = sum((Decimal(call.cost_usd) for call in tracked_calls if call.cost_usd is not None), Decimal("0"))
    return {
        "tracked_llm_api_cost_usd": float(cost) if cost_available else None,
        "tracked_llm_api_latency_ms": sum(call.latency_ms for call in tracked_calls),
        "tracked_llm_api_input_tokens": sum(call.input_tokens for call in tracked_calls),
        "tracked_llm_api_cached_input_tokens": sum(call.cached_input_tokens for call in tracked_calls),
        "tracked_llm_api_output_tokens": sum(call.output_tokens for call in tracked_calls),
        "tracked_llm_api_cost_status": "available" if cost_available else "unavailable",
        "tracked_llm_api_latency_status": "available",
        "tracked_llm_api_explanation": caveat if cost_available else "A linked LLM API call has unknown pricing; cost is unavailable. " + caveat,
    }


def _investigation_payload(
    investigation: Investigation, attempt_count: int, tracked_metrics: dict[str, object] | None = None
) -> dict[str, object]:
    tracked_metrics = tracked_metrics or _tracked_llm_metrics([])
    return {
        "id": investigation.id,
        "repository": investigation.repository,
        "issue_number": investigation.issue_number,
        "issue_title": investigation.issue_title,
        "status": investigation.status.value,
        "classification": investigation.classification.value if investigation.classification else None,
        "asserts_failure": investigation.asserts_failure,
        "validation_reason": investigation.validation_reason,
        "attempt_count": attempt_count,
        "started_at": _timestamp(investigation.created_at),
        "updated_at": _timestamp(investigation.updated_at),
        "completed_at": _timestamp(investigation.classification_completed_at),
        "duration_seconds": _duration_seconds(investigation),
        # Legacy generic cost is kept for compatibility, but now has the same
        # honest OpenAI-only availability semantics as the tracked metric.
        "cost_usd": tracked_metrics["tracked_llm_api_cost_usd"],
        **tracked_metrics,
    }


def _get_investigation(session: Session, investigation_id: str) -> Investigation:
    investigation = session.get(Investigation, investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return investigation


@router.get("")
def list_investigations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    classification: Classification | None = None,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    statement = select(Investigation)
    count_statement = select(func.count()).select_from(Investigation)
    if classification is not None:
        statement = statement.where(Investigation.classification == classification)
        count_statement = count_statement.where(Investigation.classification == classification)
    investigations = list(
        session.scalars(
            statement.order_by(Investigation.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    )
    counts = dict(
        session.execute(
            select(Hypothesis.investigation_id, func.count(Hypothesis.id)).group_by(Hypothesis.investigation_id)
        ).all()
    )
    calls_by_investigation: dict[str, list[LLMCall]] = {}
    if investigations:
        for call in session.scalars(select(LLMCall).where(LLMCall.investigation_id.in_([item.id for item in investigations]))):
            if call.investigation_id is not None:
                calls_by_investigation.setdefault(call.investigation_id, []).append(call)
    return {
        "items": [
            _investigation_payload(item, counts.get(item.id, 0), _tracked_llm_metrics(calls_by_investigation.get(item.id, [])))
            for item in investigations
        ],
        "page": page,
        "page_size": page_size,
        "total": session.scalar(count_statement) or 0,
    }


@router.get("/{investigation_id}")
def get_investigation(investigation_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    investigation = _get_investigation(session, investigation_id)
    attempt_count = session.scalar(
        select(func.count()).select_from(Hypothesis).where(Hypothesis.investigation_id == investigation.id)
    ) or 0
    calls = list(session.scalars(select(LLMCall).where(LLMCall.investigation_id == investigation.id)))
    return _investigation_payload(investigation, attempt_count, tracked_metrics=_tracked_llm_metrics(calls))


@router.get("/{investigation_id}/timeline")
def get_timeline(investigation_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    investigation = _get_investigation(session, investigation_id)
    hypotheses = list(
        session.scalars(
            select(Hypothesis)
            .where(Hypothesis.investigation_id == investigation.id)
            .order_by(Hypothesis.attempt_number)
        )
    )
    artifacts = list(session.scalars(select(Artifact).where(Artifact.investigation_id == investigation.id)))
    artifact_attempts = {
        int(part.removeprefix("attempt_"))
        for artifact in artifacts
        for part in artifact.path.split("/")
        if part.startswith("attempt_") and part.removeprefix("attempt_").isdigit()
    }
    return {
        "items": [
            {
                "attempt_number": hypothesis.attempt_number,
                "hypothesis": hypothesis.statement,
                "revision_reason": hypothesis.revision_reason,
                "action": "Codex investigation and pytest execution",
                "result": "Evidence captured" if hypothesis.attempt_number in artifact_attempts else "Evidence unavailable",
                "duration_ms": None,
            }
            for hypothesis in hypotheses
        ]
    }


@router.get("/{investigation_id}/summary")
def get_summary(investigation_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    investigation = _get_investigation(session, investigation_id)
    attempts = session.scalar(
        select(func.count()).select_from(Hypothesis).where(Hypothesis.investigation_id == investigation.id)
    ) or 0
    calls = list(session.scalars(select(LLMCall).where(LLMCall.investigation_id == investigation.id)))
    tracked_metrics = _tracked_llm_metrics(calls)
    return {
        **_investigation_payload(investigation, attempts, tracked_metrics=tracked_metrics),
        "total_duration_seconds": _duration_seconds(investigation),
        "input_tokens": tracked_metrics["tracked_llm_api_input_tokens"],
        "cached_input_tokens": tracked_metrics["tracked_llm_api_cached_input_tokens"],
        "output_tokens": tracked_metrics["tracked_llm_api_output_tokens"],
        "total_tokens": (
            int(tracked_metrics["tracked_llm_api_input_tokens"]) + int(tracked_metrics["tracked_llm_api_output_tokens"])
            if tracked_metrics["tracked_llm_api_input_tokens"] is not None else None
        ),
        "cache_hit_percent": (
            round((int(tracked_metrics["tracked_llm_api_cached_input_tokens"]) / int(tracked_metrics["tracked_llm_api_input_tokens"])) * 100, 2)
            if tracked_metrics["tracked_llm_api_input_tokens"] else None
        ),
        "latency_ms": tracked_metrics["tracked_llm_api_latency_ms"],
    }
