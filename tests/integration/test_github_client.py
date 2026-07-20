import io
import json

from triage.github.client import GitHubClient
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
