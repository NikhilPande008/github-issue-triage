from triage.github.service import GitHubIssueService


class FakeIssueSource:
    repository = "psf/requests"

    def fetch_issue(self, issue_number: int) -> dict:
        return issue_payload(issue_number)

    def fetch_comments(self, issue_number: int) -> list[dict]:
        return [{"user": {"login": "commenter"}, "body": "comment", "created_at": "2026-01-01T00:00:00Z"}]

    def fetch_latest_open_issues(self, limit: int, start_page: int = 1) -> list[dict]:
        assert start_page == 1
        return [issue_payload(3), issue_payload(2)][:limit]


def issue_payload(number: int) -> dict:
    return {
        "number": number,
        "title": f"Issue {number}",
        "body": "details",
        "user": {"login": "reporter"},
        "labels": [],
        "state": "open",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "html_url": f"https://github.com/psf/requests/issues/{number}",
    }


def test_service_fetches_and_normalizes_one_issue() -> None:
    issue = GitHubIssueService(FakeIssueSource()).fetch_issue(123)
    assert issue.issue_number == 123
    assert issue.comments[0].body == "comment"


def test_service_fetches_latest_open_issues() -> None:
    issues = GitHubIssueService(FakeIssueSource()).fetch_latest_open_issues(2)
    assert [issue.issue_number for issue in issues] == [3, 2]
