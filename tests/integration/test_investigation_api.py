import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from triage.api.main import app
from triage.api.routes.investigations import get_session
from triage.domain.enums import Classification, InvestigationStatus
from triage.persistence.database import Base, create_session_factory
from triage.persistence.models import Artifact, Hypothesis, Investigation, LLMCall


def test_read_only_investigation_endpoints(tmp_path) -> None:
    factory = create_session_factory(f"sqlite:///{tmp_path / 'dashboard.db'}")
    Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        now = datetime.now(timezone.utc)
        investigation = Investigation(
            repository="psf/requests", issue_number=123, issue_title="TLS issue", status=InvestigationStatus.COMPLETED,
            classification=Classification.REPRODUCED, asserts_failure=True, validation_reason="Changed test assertion failed.",
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
            listed = await client.get("/investigations?classification=REPRODUCED")
            assert listed.status_code == 200
            assert listed.json()["total"] == 1
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
