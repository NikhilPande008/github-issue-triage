import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class GitHubClientError(RuntimeError):
    pass


class GitHubClient:
    """Small GitHub REST client for one configured repository."""

    api_base_url = "https://api.github.com"

    def __init__(self, repository: str, token: str | None = None):
        self.repository = repository
        self.token = token

    def fetch_issue(self, issue_number: int) -> dict[str, Any]:
        return self._get(f"/repos/{self.repository}/issues/{issue_number}")

    def fetch_comments(self, issue_number: int) -> list[dict[str, Any]]:
        return self._get(f"/repos/{self.repository}/issues/{issue_number}/comments?per_page=100")

    def fetch_latest_open_issues(self, limit: int, start_page: int = 1) -> list[dict[str, Any]]:
        """Return newest open issues, excluding pull requests, across GitHub pages."""
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        if start_page < 1:
            raise ValueError("start_page must be at least 1")
        selected: list[dict[str, Any]] = []
        page = start_page
        while len(selected) < limit:
            query = urlencode({"state": "open", "sort": "created", "direction": "desc", "per_page": 100, "page": page})
            issues = self._get(f"/repos/{self.repository}/issues?{query}")
            selected.extend(issue for issue in issues if "pull_request" not in issue)
            if len(issues) < 100:
                break
            page += 1
        return selected[:limit]

    def _get(self, path: str) -> Any:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-issue-triage",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(f"{self.api_base_url}{path}", headers=headers)
        try:
            with urlopen(request, timeout=20) as response:  # noqa: S310 -- fixed GitHub API base URL
                return json.load(response)
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise GitHubClientError(f"GitHub API returned HTTP {error.code}: {detail}") from error
        except URLError as error:
            raise GitHubClientError(f"GitHub API request failed: {error.reason}") from error
