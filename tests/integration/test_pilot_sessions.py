import json

from fastapi.testclient import TestClient

from triage.api.main import app


def test_pilot_login_uses_httponly_cookie_csrf_and_logout(monkeypatch) -> None:
    monkeypatch.setenv("PILOT_REVIEW_ENABLED", "true")
    monkeypatch.setenv("PILOT_SESSION_SECURE_COOKIE", "false")
    monkeypatch.setenv("PILOT_REVIEWER_REGISTRY", json.dumps({"reviewer-a": {"cohort": "MAINTAINER", "token": "secret", "posting_approver": True}}))
    with TestClient(app) as client:
        assert client.get("/pilot-review/queue").status_code == 401
        assert client.post("/pilot-review/login", json={"reviewer_id": "reviewer-a", "token": "wrong"}).status_code == 403
        login = client.post("/pilot-review/login", json={"reviewer_id": "reviewer-a", "token": "secret"})
        assert login.status_code == 200
        assert "secret" not in login.text
        cookie = login.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie
        csrf = login.json()["csrf_token"]
        assert client.get("/pilot-review/me").json()["reviewer"]["external_id"] == "reviewer-a"
        assert client.post("/pilot-review/logout").status_code == 403
        assert client.post("/pilot-review/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
        assert client.get("/pilot-review/me").status_code == 401


def test_disabled_pilot_has_no_login_or_queue(monkeypatch) -> None:
    monkeypatch.setenv("PILOT_REVIEW_ENABLED", "false")
    with TestClient(app) as client:
        assert client.post("/pilot-review/login", json={"reviewer_id": "x", "token": "x"}).status_code == 404
        assert client.get("/pilot-review/queue").status_code == 404
