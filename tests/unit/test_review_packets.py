import hashlib
import json
from datetime import datetime, timezone

from triage.domain.enums import Classification, InvestigationStatus
from triage.persistence.database import Base, create_session_factory
from triage.persistence.models import Artifact, Investigation, LLMCall, ReviewPacket
from triage.review_packets import ReviewPacketService, canonical_json, packet_hash


def _ready_investigation(session, tmp_path):
    investigation = Investigation(repository="example/repo", issue_number=7, issue_title="Token: should not leak", status=InvestigationStatus.COMPLETED, classification=Classification.BEHAVIOR_GAP_CONFIRMED, classification_model="deterministic-validator", asserts_failure=True, validation_reason="focused failure")
    session.add(investigation)
    session.flush()
    paths = {
        "extraction_json": tmp_path / "extraction.json",
        "git_diff": tmp_path / "git.diff",
        "structured_test_results_junit": tmp_path / "junit.xml",
        "reproducibility_manifest": tmp_path / "manifest.json",
        "terminal_log": tmp_path / "terminal.log",
    }
    paths["extraction_json"].write_text(json.dumps({"summary": "reported behavior", "actual_behavior": "wrong"}), encoding="utf-8")
    paths["git_diff"].write_text("diff --git a/test.py b/test.py\n+" + "x" * 100, encoding="utf-8")
    paths["structured_test_results_junit"].write_text("<testsuite tests='1'><testcase><failure/></testcase></testsuite>", encoding="utf-8")
    paths["reproducibility_manifest"].write_text(json.dumps({"command": "python -m pytest tests/test.py"}), encoding="utf-8")
    paths["terminal_log"].write_text("secret=never include me", encoding="utf-8")
    for kind, path in paths.items():
        session.add(Artifact(investigation_id=investigation.id, kind=kind, path=str(path)))
    session.add(LLMCall(investigation_id=investigation.id, provider="openai", model="test-model", pricing_version="v1", purpose="issue_extraction", input_tokens=1, cached_input_tokens=0, output_tokens=1, latency_ms=1))
    session.commit()
    return investigation, paths


def test_packet_snapshots_bounded_evidence_and_remains_stable(tmp_path) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'packets.db'}")
    Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        investigation, paths = _ready_investigation(session, tmp_path)
        packet = ReviewPacketService(session).issue(investigation.id)
        snapshot = json.loads(packet.snapshot_json)
        assert snapshot["issue_body"] is None
        assert "terminal_log" not in packet.snapshot_json
        assert snapshot["generated_test_diff"]["sha256"] == hashlib.sha256(paths["git_diff"].read_bytes()).hexdigest()
        assert snapshot["structured_junit_result"]["artifact_id"]
        assert snapshot["runner"]["command"] == "python -m pytest tests/test.py"
        assert packet.integrity_hash == packet_hash(snapshot)
        paths["git_diff"].write_text("changed live file", encoding="utf-8")
        persisted = session.get(ReviewPacket, packet.id)
        assert persisted.snapshot_json == packet.snapshot_json
        assert persisted.integrity_hash == packet.integrity_hash


def test_packet_hash_is_canonical_and_reissues_preserve_older_versions(tmp_path) -> None:
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})
    assert packet_hash({"b": 1, "a": 2}) == packet_hash({"a": 2, "b": 1})
    factory = create_session_factory(f"sqlite:///{tmp_path / 'versions.db'}")
    Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        investigation, _ = _ready_investigation(session, tmp_path)
        service = ReviewPacketService(session)
        first = service.issue(investigation.id)
        assert service.issue(investigation.id).id == first.id
        second = service.issue(investigation.id, reissue=True)
        assert (first.version, second.version) == (1, 2)
        assert session.get(ReviewPacket, first.id).snapshot_json == first.snapshot_json
        first.schema_version = "mutated"
        try:
            session.commit()
        except ValueError:
            session.rollback()
        else:
            raise AssertionError("Review packet update unexpectedly succeeded")


def test_packet_failure_only_records_operational_state(tmp_path) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'failure.db'}")
    Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        investigation = Investigation(repository="x/y", issue_number=1, status=InvestigationStatus.RUNNING, classification=Classification.NEEDS_INFO, asserts_failure=False, validation_reason="missing evidence")
        session.add(investigation); session.commit()
        assert ReviewPacketService(session).issue_safely(investigation.id) is None
        assert investigation.status == InvestigationStatus.RUNNING
        assert investigation.classification == Classification.NEEDS_INFO
        assert investigation.review_packet_status == "UNAVAILABLE"
