from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from triage.api.routes.investigations import _get_investigation, _timestamp, get_session
from triage.persistence.models import Artifact

router = APIRouter(prefix="/investigations", tags=["artifacts"])


def _artifact_payload(artifact: Artifact) -> dict[str, object]:
    path = Path(artifact.path)
    try:
        stat = path.stat()
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return {
            "id": artifact.id,
            "kind": artifact.kind,
            "path": artifact.path,
            "available": False,
            "content": None,
            "size_bytes": None,
            "modified_at": None,
            "error": f"Artifact is unavailable: {error}",
        }
    return {
        "id": artifact.id,
        "kind": artifact.kind,
        "path": artifact.path,
        "available": True,
        "content": content,
        "size_bytes": stat.st_size,
        "modified_at": _timestamp(datetime.fromtimestamp(stat.st_mtime).astimezone()),
        "error": None,
    }


@router.get("/{investigation_id}/artifacts")
def get_artifacts(investigation_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    _get_investigation(session, investigation_id)
    artifacts = list(
        session.scalars(
            select(Artifact).where(Artifact.investigation_id == investigation_id).order_by(Artifact.created_at)
        )
    )
    return {"items": [_artifact_payload(artifact) for artifact in artifacts]}
