from datetime import datetime

from pydantic import BaseModel


class GitHubComment(BaseModel):
    author: str
    body: str
    created_at: datetime


class GitHubIssue(BaseModel):
    repository: str
    issue_number: int
    title: str
    body: str
    author: str
    labels: list[str]
    comments: list[GitHubComment]
    state: str
    created_at: datetime
    updated_at: datetime
    url: str


class GitHubIssuePage(BaseModel):
    """One GitHub issues API page after pull requests have been excluded."""

    issues: list[GitHubIssue]
    is_last_page: bool
