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
            repository="psf/requests", issue_number=123, status=InvestigationStatus.COMPLETED,
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
            LLMCall(investigation_id=investigation.id, model="codex", purpose="investigation", input_tokens=100, cached_input_tokens=25, output_tokens=10, cost_usd="0.001000", latency_ms=40),
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
            assert listed.json()["items"][0]["cost_usd"] == 0.001
            summary = await client.get(f"/investigations/{investigation_id}/summary")
            assert summary.json()["cache_hit_percent"] == 25.0
            assert summary.json()["cost_usd"] == 0.001
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
