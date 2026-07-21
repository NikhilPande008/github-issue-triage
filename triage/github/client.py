import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class GitHubClientError(RuntimeError):
    pass


class GitHubRateLimitError(GitHubClientError):
    """GitHub explicitly reported that the current API quota is exhausted."""


def format_rate_limit_reset(value: str | None, now: datetime | None = None) -> str | None:
    """Return a safe, human-friendly reset hint for a GitHub epoch header."""
    try:
        reset = datetime.fromtimestamp(int(value or ""), tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None
    now = now or datetime.now(timezone.utc)
    seconds = max(0, round((reset - now).total_seconds()))
    if seconds < 60:
        wait = f"{seconds}s"
    else:
        minutes, remainder = divmod(seconds, 60)
        wait = f"{minutes}m" if remainder == 0 else f"{minutes}m {remainder}s"
    return f"Retry in {wait} (at {reset.strftime('%Y-%m-%d %H:%M UTC')})."


def _is_rate_limited(status: int, headers: Any, detail: str) -> bool:
    remaining = headers.get("X-RateLimit-Remaining") if headers is not None else None
    if status == 429 or (status == 403 and str(remaining).strip() == "0"):
        return True
    message = detail.lower()
    return "rate limit exceeded" in message or "secondary rate limit" in message


def _rate_limit_message(token_configured: bool, headers: Any) -> str:
    reset = headers.get("X-RateLimit-Reset") if headers is not None else None
    action = (
        "The configured GITHUB_TOKEN quota is exhausted."
        if token_configured
        else "Set GITHUB_TOKEN to increase GitHub API rate limits."
    )
    reset_hint = format_rate_limit_reset(reset)
    return "GitHub API rate limit exhausted. " + action + (f" {reset_hint}" if reset_hint else "")


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
            issues = self.fetch_open_issues_page(page)
            selected.extend(issue for issue in issues if "pull_request" not in issue)
            if len(issues) < 100:
                break
            page += 1
        return selected[:limit]

    def fetch_open_issues_page(self, page: int) -> list[dict[str, Any]]:
        if page < 1:
            raise ValueError("page must be at least 1")
        query = urlencode({"state": "open", "sort": "created", "direction": "desc", "per_page": 100, "page": page})
        return self._get(f"/repos/{self.repository}/issues?{query}")

    def create_issue_comment(self, issue_number: int, body: str) -> dict[str, Any]:
        """The only write endpoint; callers must apply approval gates first."""
        return self._request("POST", f"/repos/{self.repository}/issues/{issue_number}/comments", {"body": body})

    def _get(self, path: str) -> Any:
        return self._request("GET", path)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-issue-triage",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(f"{self.api_base_url}{path}", headers=headers, data=data, method=method)
        try:
            with urlopen(request, timeout=20) as response:  # noqa: S310 -- fixed GitHub API base URL
                return json.load(response)
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            headers = error.headers
            if _is_rate_limited(error.code, headers, detail):
                raise GitHubRateLimitError(_rate_limit_message(bool(self.token), headers)) from error
            raise GitHubClientError(f"GitHub API returned HTTP {error.code}: {detail}") from error
        except URLError as error:
            raise GitHubClientError(f"GitHub API request failed: {error.reason}") from error
