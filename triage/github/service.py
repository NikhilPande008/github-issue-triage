from typing import Protocol

from triage.github.mapper import map_issue
from triage.github.models import GitHubIssue, GitHubIssuePage


class IssueSource(Protocol):
    repository: str

    def fetch_issue(self, issue_number: int) -> dict: ...

    def fetch_comments(self, issue_number: int) -> list[dict]: ...

    def fetch_latest_open_issues(self, limit: int, start_page: int = 1) -> list[dict]: ...


class GitHubIssueService:
    """Coordinates retrieval and normalization without applying business rules."""

    def __init__(self, client: IssueSource):
        self.client = client

    def fetch_issue(self, issue_number: int) -> GitHubIssue:
        issue = self.client.fetch_issue(issue_number)
        return map_issue(self.client.repository, issue, self.client.fetch_comments(issue_number))

    def fetch_latest_open_issues(self, limit: int, start_page: int = 1) -> list[GitHubIssue]:
        issues = self.client.fetch_latest_open_issues(limit, start_page)
        return [
            map_issue(self.client.repository, issue, self.client.fetch_comments(issue["number"]))
            for issue in issues
        ]

    def fetch_open_issue_page(self, page: int) -> GitHubIssuePage:
        issues = self.client.fetch_open_issues_page(page)
        return GitHubIssuePage(
            issues=[
                map_issue(self.client.repository, issue, self.client.fetch_comments(issue["number"]))
                for issue in issues
                if "pull_request" not in issue
            ],
            is_last_page=len(issues) < 100,
        )
