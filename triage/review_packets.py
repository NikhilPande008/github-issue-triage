"""Immutable, bounded review snapshots. These are evidence packets, not verdicts."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from triage.domain.enums import InvestigationStatus
from triage.persistence.models import Artifact, Investigation, LLMCall, ReviewPacket, WebhookJob

PACKET_SCHEMA_VERSION = "1.0"
MAX_EXCERPT_BYTES = 16_000
MAX_TEXT_CHARS = 8_000
_SECRET = re.compile(r"(?i)(authorization|token|secret|password|api[_-]?key)\s*[:=]\s*[^\s,]+")


def canonical_json(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def packet_hash(snapshot: dict[str, object]) -> str:
    return hashlib.sha256(canonical_json(snapshot).encode("utf-8")).hexdigest()


def _safe_text(value: str | None, limit: int = MAX_TEXT_CHARS) -> str | None:
    if value is None:
        return None
    return _SECRET.sub(r"\1: [redacted]", value.replace("\x00", ""))[:limit]


def _bounded_json(value: object, depth: int = 0) -> object:
    """Keep persisted extraction useful without copying arbitrary model output."""
    if depth >= 8:
        return "[truncated]"
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, list):
        return [_bounded_json(item, depth + 1) for item in value[:100]]
    if isinstance(value, dict):
        return {str(key)[:128]: _bounded_json(item, depth + 1) for key, item in list(value.items())[:100]}
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _safe_text(str(value))


def _artifact_snapshot(artifact: Artifact | None, *, include_excerpt: bool = False) -> dict[str, object] | None:
    if artifact is None:
        return None
    result: dict[str, object] = {"artifact_id": artifact.id, "path": artifact.path, "sha256": None, "size_bytes": None}
    try:
        content = Path(artifact.path).read_bytes()
    except OSError:
        result["availability"] = "UNAVAILABLE_AT_ISSUANCE"
        return result
    result.update({"availability": "AVAILABLE_AT_ISSUANCE", "sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)})
    if include_excerpt:
        result["content_excerpt"] = _safe_text(content[:MAX_EXCERPT_BYTES].decode("utf-8", errors="replace"), MAX_EXCERPT_BYTES)
        result["content_truncated"] = len(content) > MAX_EXCERPT_BYTES
    return result


def _latest(artifacts: list[Artifact], kind: str) -> Artifact | None:
    choices = [artifact for artifact in artifacts if artifact.kind == kind]
    return choices[-1] if choices else None


class ReviewPacketService:
    def __init__(self, session: Session):
        self.session = session

    def issue(self, investigation_id: str, *, reissue: bool = False) -> ReviewPacket:
        investigation = self.session.get(Investigation, investigation_id)
        if investigation is None:
            raise ValueError("Investigation not found")
        if investigation.status not in {
            InvestigationStatus.COMPLETED,
            InvestigationStatus.COMPLETED_NO_GAP,
            InvestigationStatus.FAILED,
        } or investigation.classification is None:
            raise ValueError("Review packets require a terminal, classified investigation")
        existing = list(self.session.scalars(select(ReviewPacket).where(ReviewPacket.investigation_id == investigation_id).order_by(ReviewPacket.version)))
        if existing and not reissue:
            return existing[-1]
        snapshot = self._snapshot(investigation)
        packet = ReviewPacket(
            investigation_id=investigation_id,
            version=(existing[-1].version + 1 if existing else 1),
            schema_version=PACKET_SCHEMA_VERSION,
            snapshot_json=canonical_json(snapshot),
            integrity_hash=packet_hash(snapshot),
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(packet)
        investigation.review_packet_status = "ISSUED"
        investigation.review_packet_reason = None
        self.session.commit()
        self.session.refresh(packet)
        return packet

    def issue_safely(self, investigation_id: str) -> ReviewPacket | None:
        """Packet failure remains operational metadata, never a pipeline failure."""
        try:
            return self.issue(investigation_id)
        except Exception as error:
            # This also keeps the best-effort boundary safe for callers whose
            # persistence session has already failed or is a lightweight test double.
            try:
                investigation = self.session.get(Investigation, investigation_id)
                if investigation is not None:
                    investigation.review_packet_status = "UNAVAILABLE"
                    investigation.review_packet_reason = _safe_text(str(error), 1000)
                    self.session.commit()
            except Exception:
                pass
            return None

    def _snapshot(self, investigation: Investigation) -> dict[str, object]:
        artifacts = list(self.session.scalars(select(Artifact).where(Artifact.investigation_id == investigation.id).order_by(Artifact.created_at, Artifact.id)))
        extraction = _artifact_snapshot(_latest(artifacts, "extraction_json"))
        if extraction and extraction["availability"] == "AVAILABLE_AT_ISSUANCE":
            try:
                extraction["structured_output"] = _bounded_json(json.loads(Path(str(extraction["path"])).read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                extraction["structured_output"] = None
        manifest = _artifact_snapshot(_latest(artifacts, "reproducibility_manifest"))
        job = self.session.scalar(select(WebhookJob).where(WebhookJob.investigation_id == investigation.id).order_by(WebhookJob.created_at.desc()))
        calls = list(self.session.scalars(select(LLMCall).where(LLMCall.investigation_id == investigation.id).order_by(LLMCall.created_at, LLMCall.id)))
        models = [{"purpose": call.purpose, "provider": call.provider, "model": call.model, "pricing_version": call.pricing_version} for call in calls]
        return {
            "packet_schema_version": PACKET_SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "investigation": {"id": investigation.id, "repository": investigation.repository, "issue_number": investigation.issue_number, "issue_title": _safe_text(investigation.issue_title)},
            "issue_body": None,  # Raw issue bodies are not persisted by this system.
            "extraction": extraction,
            "runner": {"id": investigation.test_runner, "command": self._manifest_command(manifest)},
            "generated_test_diff": _artifact_snapshot(_latest(artifacts, "git_diff"), include_excerpt=True),
            "structured_junit_result": _artifact_snapshot(_latest(artifacts, "structured_test_results_junit")),
            "deterministic_validation": {"asserts_failure": investigation.asserts_failure, "reason": _safe_text(investigation.validation_reason)},
            "classification": {"primary": investigation.classification.value, "asserts_failure": investigation.asserts_failure},
            "proposed_maintainer_comment": _safe_text(job.proposed_comment_body if job else None),
            "reproducibility_manifest": manifest,
            "versions": {"models": models, "classification_model": investigation.classification_model, "validator_policy": "deterministic-validator-v1", "runner": investigation.test_runner},
        }

    @staticmethod
    def _manifest_command(manifest: dict[str, object] | None) -> object:
        if not manifest or manifest.get("availability") != "AVAILABLE_AT_ISSUANCE":
            return None
        try:
            data = json.loads(Path(str(manifest["path"])).read_text(encoding="utf-8"))
            return _safe_text(str(data.get("command")), 1000) if data.get("command") else None
        except (OSError, json.JSONDecodeError):
            return None
