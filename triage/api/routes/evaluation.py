from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from triage.api.routes.investigations import get_session
from triage.persistence.models import Investigation
from triage.retrospective_evaluation import DatasetError, load

router = APIRouter(prefix="/evaluation", tags=["evaluation"])
DATASET = Path(__file__).resolve().parents[3] / "demo" / "evaluations" / "retrospective-v1.json"


@router.get("/retrospective")
def retrospective(session: Session = Depends(get_session)) -> dict:
    ids = set(session.scalars(select(Investigation.id)))
    try: data = load(DATASET, ids)
    except DatasetError as error: return {"status": "invalid", "reason": str(error)}
    return {"status": "no_data" if not data["cases"] else "available", "dataset": data}
