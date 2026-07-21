"""Advisory similarity layer; it never changes primary classification."""

import hashlib
import json
import re
from pathlib import Path

from sqlalchemy import select

from triage.config.settings import Settings
from triage.persistence.models import Artifact, DuplicateCandidate, Investigation, SimilarityDocument
from triage.similarity.embeddings import cosine_similarity

DOCUMENT_VERSION = "v1"
SCORING_VERSION = "exact-v1"


class DuplicateSimilarityService:
    def __init__(self, session, settings: Settings, embedding_provider=None):
        self.session, self.settings = session, settings
        self.embedding_provider = embedding_provider

    def analyze(self, investigation_id: str) -> list[DuplicateCandidate]:
        if not self.settings.duplicate_detection_enabled:
            return []
        investigation = self.session.get(Investigation, investigation_id)
        if investigation is None or investigation.status.value != "COMPLETED":
            return []
        source = self._upsert_document(investigation)
        documents = list(self.session.scalars(select(SimilarityDocument).where(SimilarityDocument.repository == investigation.repository, SimilarityDocument.investigation_id != investigation.id)))
        candidates: list[DuplicateCandidate] = []
        for other in documents:
            score, signals = _exact_score(source, other)
            if self.embedding_provider and source.embedding_vector and other.embedding_vector:
                semantic = cosine_similarity(json.loads(source.embedding_vector), json.loads(other.embedding_vector))
                if semantic > score:
                    score, signals = semantic, signals + ["semantic embedding similarity"]
            if score < self.settings.duplicate_similarity_threshold:
                continue
            left, right = sorted((investigation.id, other.investigation_id))
            # Canonical pair order prevents reverse duplicates.
            existing = self.session.scalar(select(DuplicateCandidate).where(DuplicateCandidate.source_investigation_id == left, DuplicateCandidate.candidate_investigation_id == right))
            if existing is None:
                existing = DuplicateCandidate(source_investigation_id=left, candidate_investigation_id=right, repository=investigation.repository, similarity_score=score, scoring_version=SCORING_VERSION, matched_signals=json.dumps(signals), status="SUGGESTED")
                self.session.add(existing)
                self.session.commit()
            candidates.append(existing)
        return candidates

    def _upsert_document(self, investigation: Investigation) -> SimilarityDocument:
        text = self.canonical_document(investigation)
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        document = self.session.scalar(select(SimilarityDocument).where(SimilarityDocument.investigation_id == investigation.id))
        if document is None:
            document = SimilarityDocument(investigation_id=investigation.id, repository=investigation.repository, document_version=DOCUMENT_VERSION, canonical_text=text, checksum=checksum, embedding_status="EXACT_ONLY" if not self.settings.duplicate_embedding_provider else "PENDING")
            self.session.add(document)
        elif document.checksum != checksum or document.document_version != DOCUMENT_VERSION:
            document.canonical_text, document.checksum, document.document_version = text, checksum, DOCUMENT_VERSION
        if self.embedding_provider:
            try:
                document.embedding_vector = json.dumps(self.embedding_provider.embed(text))
                document.embedding_provider = self.embedding_provider.provider
                document.embedding_model = self.embedding_provider.model
                document.embedding_status = "AVAILABLE"
            except Exception as error:
                document.embedding_status = "UNAVAILABLE"
                document.error_reason = str(error)[:300]
        self.session.commit()
        return document

    def canonical_document(self, investigation: Investigation) -> str:
        extraction = self._extraction(investigation.id)
        # Never use raw GitHub issue body, terminal content, or unbounded diff.
        fields = {
            "repository": investigation.repository,
            "summary": _clean(extraction.get("summary")),
            "expected": _clean(extraction.get("expected_behavior")),
            "actual": _clean(extraction.get("actual_behavior")),
            "missing": ",".join(_clean(item, 120) for item in extraction.get("missing_info", [])[:8]),
            "runner": investigation.test_runner,
            "validation": _clean(investigation.validation_reason, 400),
            "test_paths": ",".join(sorted(self._test_paths(investigation.id))),
        }
        return "\n".join(f"{key}:{value}" for key, value in fields.items() if value)

    def _extraction(self, investigation_id: str) -> dict:
        artifact = self.session.scalar(select(Artifact).where(Artifact.investigation_id == investigation_id, Artifact.kind == "extraction_json"))
        if artifact is None:
            return {}
        try:
            return json.loads(Path(artifact.path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _test_paths(self, investigation_id: str) -> set[str]:
        paths = set()
        for artifact in self.session.scalars(select(Artifact).where(Artifact.investigation_id == investigation_id, Artifact.kind == "git_diff")):
            try:
                for line in Path(artifact.path).read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.startswith("+++ b/") and ("test" in line.lower()):
                        paths.add(line.removeprefix("+++ b/"))
            except OSError:
                continue
        return paths


def _clean(value, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\x00", "")).strip()[:limit]


def _exact_score(left: SimilarityDocument, right: SimilarityDocument) -> tuple[float, list[str]]:
    if left.checksum == right.checksum:
        return 1.0, ["identical canonical evidence checksum"]
    left_lines, right_lines = set(left.canonical_text.splitlines()), set(right.canonical_text.splitlines())
    overlap = len(left_lines & right_lines) / max(1, len(left_lines | right_lines))
    signals = ["high overlap structured evidence"] if overlap >= 0.5 else []
    return overlap, signals
