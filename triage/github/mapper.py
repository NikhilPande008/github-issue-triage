from typing import Any

from triage.github.models import GitHubComment, GitHubIssue


def map_comment(payload: dict[str, Any]) -> GitHubComment:
    return GitHubComment(
        author=payload["user"]["login"],
        body=payload.get("body") or "",
        created_at=payload["created_at"],
    )


def map_issue(
    repository: str, payload: dict[str, Any], comment_payloads: list[dict[str, Any]]
) -> GitHubIssue:
    return GitHubIssue(
        repository=repository,
        issue_number=payload["number"],
        title=payload["title"],
        body=payload.get("body") or "",
        author=payload["user"]["login"],
        labels=[label["name"] for label in payload.get("labels", [])],
        comments=[map_comment(comment) for comment in comment_payloads],
        state=payload["state"],
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
        url=payload["html_url"],
    )
