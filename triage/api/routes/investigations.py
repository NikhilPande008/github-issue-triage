from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from triage.config.settings import Settings
from triage.domain.enums import Classification
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


def _investigation_payload(
    investigation: Investigation, attempt_count: int, cost_usd: Decimal | int = 0
) -> dict[str, object]:
    return {
        "id": investigation.id,
        "repository": investigation.repository,
        "issue_number": investigation.issue_number,
        "status": investigation.status.value,
        "classification": investigation.classification.value if investigation.classification else None,
        "asserts_failure": investigation.asserts_failure,
        "validation_reason": investigation.validation_reason,
        "attempt_count": attempt_count,
        "started_at": _timestamp(investigation.created_at),
        "updated_at": _timestamp(investigation.updated_at),
        "duration_seconds": _duration_seconds(investigation),
        "cost_usd": float(Decimal(cost_usd)),
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
    costs = dict(
        session.execute(
            select(LLMCall.investigation_id, func.coalesce(func.sum(LLMCall.cost_usd), 0))
            .where(LLMCall.investigation_id.is_not(None))
            .group_by(LLMCall.investigation_id)
        ).all()
    )
    return {
        "items": [
            _investigation_payload(item, counts.get(item.id, 0), costs.get(item.id, 0))
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
    return _investigation_payload(investigation, attempt_count)


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
    totals = session.execute(
        select(
            func.coalesce(func.sum(LLMCall.input_tokens), 0),
            func.coalesce(func.sum(LLMCall.cached_input_tokens), 0),
            func.coalesce(func.sum(LLMCall.output_tokens), 0),
            func.coalesce(func.sum(LLMCall.cost_usd), 0),
            func.coalesce(func.sum(LLMCall.latency_ms), 0),
        ).where(LLMCall.investigation_id == investigation.id)
    ).one()
    input_tokens, cached_input_tokens, output_tokens, cost_usd, latency_ms = totals
    input_tokens = int(input_tokens)
    cached_input_tokens = int(cached_input_tokens)
    output_tokens = int(output_tokens)
    return {
        **_investigation_payload(investigation, attempts),
        "total_duration_seconds": _duration_seconds(investigation),
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cache_hit_percent": round((cached_input_tokens / input_tokens) * 100, 2) if input_tokens else None,
        "cost_usd": float(Decimal(cost_usd)),
        "latency_ms": int(latency_ms),
    }
