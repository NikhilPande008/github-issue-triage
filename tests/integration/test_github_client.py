import io
import json
from datetime import datetime, timezone
from email.message import Message
from urllib.error import HTTPError

import pytest

from triage.github.client import GitHubClient, GitHubClientError, GitHubRateLimitError, format_rate_limit_reset
import triage.github.client as client_module


class FakeResponse:
    def __init__(self, payload: object):
        self.payload = payload

    def __enter__(self):
        return io.BytesIO(json.dumps(self.payload).encode("utf-8"))

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def test_client_uses_authentication_and_fetches_issue(monkeypatch) -> None:
    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse({"number": 123})

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)
    issue = GitHubClient("psf/requests", "token").fetch_issue(123)

    assert issue == {"number": 123}
    assert requests[0][0].full_url == "https://api.github.com/repos/psf/requests/issues/123"
    assert requests[0][0].get_header("Authorization") == "Bearer token"


def test_client_lists_open_issues_and_filters_pull_requests(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        return FakeResponse([{"number": 2}, {"number": 1, "pull_request": {"url": "example"}}])

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)
    issues = GitHubClient("psf/requests").fetch_latest_open_issues(2)

    assert issues == [{"number": 2}]


def test_client_paginates_when_pull_requests_fill_the_first_page(monkeypatch) -> None:
    requests = []
    first_page = [{"number": number, "pull_request": {"url": "example"}} for number in range(100)]
    second_page = [{"number": 202}, {"number": 201}]

    def fake_urlopen(request, timeout):
        requests.append(request.full_url)
        return FakeResponse(first_page if request.full_url.endswith("page=1") else second_page)

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)
    issues = GitHubClient("psf/requests").fetch_latest_open_issues(2)

    assert issues == second_page
    assert len(requests) == 2


def _headers(**values: str) -> Message:
    headers = Message()
    for name, value in values.items():
        headers[name.replace("_", "-")] = value
    return headers


def test_client_detects_403_rate_limit_header_without_exposing_token(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise HTTPError(
            request.full_url, 403, "Forbidden", _headers(X_RateLimit_Remaining="0"), io.BytesIO(b'{"message":"Forbidden"}')
        )

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)
    with pytest.raises(GitHubRateLimitError, match="Set GITHUB_TOKEN to increase GitHub API rate limits"):
        GitHubClient("psf/requests").fetch_issue(1)


def test_client_detects_429_and_explains_configured_token_quota(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 429, "Too Many Requests", _headers(), io.BytesIO(b"{}"))

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)
    with pytest.raises(GitHubRateLimitError, match="configured GITHUB_TOKEN quota is exhausted") as error:
        GitHubClient("psf/requests", "secret-token").fetch_issue(1)
    assert "secret-token" not in str(error.value)


def test_client_detects_github_rate_limit_message_without_headers(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 403, "Forbidden", None, io.BytesIO(b'{"message":"API rate limit exceeded"}'))

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)
    with pytest.raises(GitHubRateLimitError):
        GitHubClient("psf/requests").fetch_issue(1)


def test_client_does_not_misclassify_ordinary_403(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 403, "Forbidden", _headers(), io.BytesIO(b'{"message":"Resource not accessible"}'))

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)
    with pytest.raises(GitHubClientError, match="HTTP 403") as error:
        GitHubClient("psf/requests").fetch_issue(1)
    assert not isinstance(error.value, GitHubRateLimitError)


def test_rate_limit_reset_formatting_is_human_friendly_and_safe() -> None:
    now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    assert format_rate_limit_reset("1784635320", now) == "Retry in 2m (at 2026-07-21 12:02 UTC)."
    assert format_rate_limit_reset("not-an-epoch", now) is None
    assert format_rate_limit_reset(None, now) is None
