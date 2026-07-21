import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx

from triage.api.main import app
from triage.api.routes.investigations import get_session
from triage.domain.enums import Classification, InvestigationStatus, WebhookJobStatus
from triage.persistence.database import Base, create_session_factory
from triage.persistence.models import Artifact, Hypothesis, Investigation, LLMCall, WebhookJob
from triage.persistence.models import ReviewPacket
from triage.review_packets import canonical_json, packet_hash


def test_read_only_investigation_endpoints(tmp_path) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'dashboard.db'}")
    Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        now = datetime.now(timezone.utc)
        investigation = Investigation(
            repository="psf/requests", issue_number=123, issue_title="TLS issue", status=InvestigationStatus.COMPLETED,
            classification=Classification.BEHAVIOR_GAP_CONFIRMED, asserts_failure=True, validation_reason="Changed test assertion failed.",
            created_at=now, updated_at=now + timedelta(seconds=3), classification_completed_at=now + timedelta(seconds=3),
        )
        session.add(investigation)
        session.flush()
        artifact_path = tmp_path / "attempt_1" / "pytest_output.txt"
        artifact_path.parent.mkdir()
        artifact_path.write_text("FAILED tests/test_example.py::test_regression", encoding="utf-8")
        session.add_all([
            Hypothesis(investigation_id=investigation.id, attempt_number=1, statement="Exercise the regression."),
            Artifact(investigation_id=investigation.id, kind="pytest_output", path=str(artifact_path)),
            Artifact(investigation_id=investigation.id, kind="git_diff", path=str(tmp_path / "deleted.diff")),
            LLMCall(investigation_id=investigation.id, provider="openai", model="gpt-5.6-luna", pricing_version="2026-07-20", purpose="issue_extraction", input_tokens=100, cached_input_tokens=25, output_tokens=10, cost_usd="0.001000", latency_ms=40),
            LLMCall(investigation_id=investigation.id, provider="openai", model="gpt-5.6-luna", pricing_version="2026-07-20", purpose="evidence_classification", input_tokens=50, cached_input_tokens=0, output_tokens=5, cost_usd="0.002000", latency_ms=60),
            LLMCall(investigation_id=investigation.id, provider="codex", model="codex", purpose="investigation", input_tokens=0, cached_input_tokens=0, output_tokens=0, cost_usd=None, latency_ms=999),
        ])
        session.commit()
        investigation_id = investigation.id

    def override_session():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session

    async def request() -> None:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            listed = await client.get("/investigations?classification=BEHAVIOR_GAP_CONFIRMED")
            assert listed.status_code == 200
            assert listed.json()["total"] == 1
            assert listed.json()["items"][0]["classification"] == "BEHAVIOR_GAP_CONFIRMED"
            assert listed.json()["items"][0]["attempt_count"] == 1
            assert listed.json()["items"][0]["tracked_llm_api_cost_usd"] == 0.003
            assert listed.json()["items"][0]["tracked_llm_api_latency_ms"] == 100
            assert "Codex usage is excluded" in listed.json()["items"][0]["tracked_llm_api_explanation"]
            assert listed.json()["items"][0]["issue_title"] == "TLS issue"
            summary = await client.get(f"/investigations/{investigation_id}/summary")
            assert summary.json()["cache_hit_percent"] == 16.67
            assert summary.json()["tracked_llm_api_cost_usd"] == 0.003
            assert summary.json()["latency_ms"] == 100
            timeline = await client.get(f"/investigations/{investigation_id}/timeline")
            assert timeline.json()["items"][0]["result"] == "Evidence captured"
            artifacts = await client.get(f"/investigations/{investigation_id}/artifacts")
            artifacts_by_kind = {item["kind"]: item for item in artifacts.json()["items"]}
            assert artifacts_by_kind["pytest_output"]["content"].startswith("FAILED")
            assert artifacts_by_kind["git_diff"]["available"] is False
            assert (await client.get("/investigations/missing")).status_code == 404

    try:
        asyncio.run(request())
    finally:
        app.dependency_overrides.clear()


def test_review_packet_endpoints_are_read_only_and_honest_when_absent(tmp_path) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'review-api.db'}")
    Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        legacy = Investigation(repository="example/repo", issue_number=1, status=InvestigationStatus.COMPLETED)
        issued = Investigation(repository="example/repo", issue_number=2, status=InvestigationStatus.COMPLETED)
        session.add_all([legacy, issued]); session.flush()
        snapshot = {"packet_schema_version": "1.0", "investigation": {"id": issued.id}}
        packet = ReviewPacket(investigation_id=issued.id, version=1, schema_version="1.0", snapshot_json=canonical_json(snapshot), integrity_hash=packet_hash(snapshot), created_at=datetime.now(timezone.utc))
        session.add(packet); session.commit()
        legacy_id, issued_id, packet_id = legacy.id, issued.id, packet.id

    def override_session():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    async def request() -> None:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            absent = await client.get(f"/investigations/{legacy_id}/review-packets")
            assert absent.status_code == 200 and absent.json()["status"] == "NOT_ISSUED"
            listed = await client.get(f"/investigations/{issued_id}/review-packets")
            assert listed.json()["status"] == "AVAILABLE"
            assert listed.json()["items"][0]["integrity_hash"] == packet_hash(snapshot)
            detail = await client.get(f"/review-packets/{packet_id}")
            assert detail.json()["snapshot"] == snapshot
            assert (await client.post(f"/review-packets/{packet_id}")).status_code == 405
    try:
        asyncio.run(request())
    finally:
        app.dependency_overrides.clear()


def test_pilot_assessment_api_requires_verified_identity_and_preserves_verdict(tmp_path, monkeypatch) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'assessment-api.db'}")
    Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        investigation = Investigation(repository="example/repo", issue_number=5, status=InvestigationStatus.COMPLETED, classification=Classification.NEEDS_INFO, asserts_failure=False, validation_reason="unchanged")
        session.add(investigation); session.flush()
        snapshot = {"packet_schema_version": "1.0", "investigation": {"id": investigation.id}}
        packet = ReviewPacket(investigation_id=investigation.id, version=1, schema_version="1.0", snapshot_json=canonical_json(snapshot), integrity_hash=packet_hash(snapshot), created_at=datetime.now(timezone.utc))
        session.add(packet); session.commit()
        investigation_id, packet_id = investigation.id, packet.id

    def override_session():
        with factory() as session:
            yield session
    app.dependency_overrides[get_session] = override_session
    body = {"extraction_aligned": "YES", "test_aligned": "NO", "failure_supports_signal": "UNCERTAIN", "public_comment_appropriate": "NOT_ENOUGH_CONTEXT", "confidence": "MEDIUM"}
    async def request() -> None:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.post(f"/review-packets/{packet_id}/assessments", json=body)).status_code == 404
            monkeypatch.setenv("PILOT_REVIEW_ENABLED", "true")
            monkeypatch.setenv("PILOT_REVIEWER_REGISTRY", json.dumps({"reviewer-a": {"cohort": "MAINTAINER", "token": "correct"}}))
            assert (await client.post(f"/review-packets/{packet_id}/assessments", json=body, headers={"X-Pilot-Reviewer": "reviewer-a", "X-Pilot-Review-Token": "wrong"})).status_code == 403
            created = await client.post(f"/review-packets/{packet_id}/assessments", json=body, headers={"X-Pilot-Reviewer": "reviewer-a", "X-Pilot-Review-Token": "correct"})
            assert created.status_code == 201
            assert created.json()["packet_version"] == 1
            assert (await client.get(f"/review-packets/{packet_id}/assessments")).json()["items"][0]["packet_hash"]
            assert len((await client.get(f"/investigations/{investigation_id}/review-assessments")).json()["items"]) == 1
            packet_detail = await client.get(f"/review-packets/{packet_id}")
            assert packet_detail.json()["current_consensus"]["state"] == "PENDING_REVIEW"
            assert len((await client.get(f"/review-packets/{packet_id}/consensus-history")).json()["items"]) == 1
    try:
        asyncio.run(request())
    finally:
        app.dependency_overrides.clear()
    with factory() as session:
        preserved = session.get(Investigation, investigation_id)
        assert preserved.classification == Classification.NEEDS_INFO
        assert preserved.asserts_failure is False and preserved.validation_reason == "unchanged"


def test_posting_approval_api_is_pilot_gated_and_server_binds_preview(tmp_path, monkeypatch) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'posting-api.db'}")
    Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        investigation = Investigation(repository="owner/repo", issue_number=9, status=InvestigationStatus.COMPLETED, classification=Classification.NEEDS_INFO, validation_reason="unchanged")
        session.add(investigation); session.flush()
        snapshot = {"packet_schema_version": "1.0", "investigation": {"id": investigation.id}}
        packet = ReviewPacket(investigation_id=investigation.id, version=1, schema_version="1.0", snapshot_json=canonical_json(snapshot), integrity_hash=packet_hash(snapshot), created_at=datetime.now(timezone.utc))
        session.add(packet); session.flush()
        session.add(WebhookJob(delivery_id="posting-api", repository="owner/repo", issue_number=9, event="issues", action="opened", status=WebhookJobStatus.QUEUED, investigation_id=investigation.id, proposed_comment_body="### Information requested\n\n- details\n\n<!-- marker -->"))
        session.commit(); investigation_id = investigation.id
    def override_session():
        with factory() as session:
            yield session
    app.dependency_overrides[get_session] = override_session
    async def request() -> None:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.post(f"/investigations/{investigation_id}/posting-approvals", json={})).status_code == 404
            monkeypatch.setenv("PILOT_REVIEW_ENABLED", "true")
            monkeypatch.setenv("PILOT_REVIEWER_REGISTRY", json.dumps({"reviewer-a": {"cohort": "INDEPENDENT_ENGINEER", "token": "correct"}}))
            assert (await client.post(f"/investigations/{investigation_id}/posting-approvals", json={}, headers={"X-Pilot-Reviewer": "reviewer-a", "X-Pilot-Review-Token": "wrong"})).status_code == 403
            created = await client.post(f"/investigations/{investigation_id}/posting-approvals", json={"rationale": "approved"}, headers={"X-Pilot-Reviewer": "reviewer-a", "X-Pilot-Review-Token": "correct"})
            assert created.status_code == 201 and created.json()["comment_body_hash"]
            assert len((await client.get(f"/investigations/{investigation_id}/posting-approvals")).json()["items"]) == 1
            assert (await client.get(f"/investigations/{investigation_id}/posting-eligibility")).json()["eligible"] is True
    try:
        asyncio.run(request())
    finally:
        app.dependency_overrides.clear()


def test_metrics_do_not_leak_and_legacy_or_unknown_costs_are_unavailable(tmp_path) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'metrics.db'}")
    Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        first = Investigation(repository="psf/requests", issue_number=1, status=InvestigationStatus.COMPLETED)
        second = Investigation(repository="psf/requests", issue_number=2, status=InvestigationStatus.COMPLETED)
        legacy = Investigation(repository="psf/requests", issue_number=3, status=InvestigationStatus.COMPLETED)
        session.add_all([first, second, legacy])
        session.flush()
        session.add_all([
            LLMCall(investigation_id=first.id, provider="openai", model="gpt-5.6-luna", pricing_version="2026-07-20", purpose="issue_extraction", input_tokens=10, cached_input_tokens=0, output_tokens=1, cost_usd="0.001000", latency_ms=100),
            LLMCall(investigation_id=first.id, provider="openai", model="unknown", pricing_version=None, purpose="retry", input_tokens=10, cached_input_tokens=0, output_tokens=1, cost_usd=None, latency_ms=200),
            LLMCall(investigation_id=second.id, provider="openai", model="gpt-5.6-luna", pricing_version="2026-07-20", purpose="issue_extraction", input_tokens=20, cached_input_tokens=0, output_tokens=2, cost_usd="0.004000", latency_ms=300),
            LLMCall(investigation_id=legacy.id, provider=None, model="codex", purpose="investigation", input_tokens=0, cached_input_tokens=0, output_tokens=0, cost_usd=0, latency_ms=400),
        ])
        session.commit()
        first_id, second_id, legacy_id = first.id, second.id, legacy.id

    def override_session():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session

    async def request() -> None:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            first_summary = (await client.get(f"/investigations/{first_id}/summary")).json()
            assert first_summary["tracked_llm_api_cost_usd"] is None
            assert first_summary["latency_ms"] == 300
            assert "unknown pricing" in first_summary["tracked_llm_api_explanation"]
            second_summary = (await client.get(f"/investigations/{second_id}/summary")).json()
            assert second_summary["tracked_llm_api_cost_usd"] == 0.004
            assert second_summary["latency_ms"] == 300
            legacy_summary = (await client.get(f"/investigations/{legacy_id}/summary")).json()
            assert legacy_summary["tracked_llm_api_cost_usd"] is None
            assert legacy_summary["cost_usd"] is None
            assert legacy_summary["latency_ms"] is None
            assert "No tracked LLM API calls" in legacy_summary["tracked_llm_api_explanation"]

    try:
        asyncio.run(request())
    finally:
        app.dependency_overrides.clear()
