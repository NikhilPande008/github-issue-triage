"""Local/internal pilot session boundary; intentionally not production SSO."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

from triage.review_assessments import PilotReviewer, verify_pilot_reviewer

COOKIE_NAME = "triage_pilot_session"

@dataclass(frozen=True)
class PilotSession:
    reviewer: PilotReviewer
    csrf_token: str
    expires_at: datetime

_sessions: dict[str, PilotSession] = {}

def create_session(registry: str, reviewer_id: str, token: str, ttl_seconds: int) -> tuple[str, PilotSession]:
    reviewer = verify_pilot_reviewer(registry, reviewer_id, token)
    session = PilotSession(reviewer, secrets.token_urlsafe(32), datetime.now(timezone.utc) + timedelta(seconds=max(60, ttl_seconds)))
    session_id = secrets.token_urlsafe(32)
    _sessions[session_id] = session
    return session_id, session

def get_session(session_id: str | None) -> PilotSession | None:
    if not session_id: return None
    item = _sessions.get(session_id)
    if item is None: return None
    expiry = item.expires_at if item.expires_at.tzinfo else item.expires_at.replace(tzinfo=timezone.utc)
    if expiry <= datetime.now(timezone.utc):
        _sessions.pop(session_id, None); return None
    return item

def destroy_session(session_id: str | None) -> None:
    if session_id: _sessions.pop(session_id, None)
