from triage.github.mapper import map_issue


def test_map_issue_normalizes_github_payload() -> None:
    issue = map_issue(
        "psf/requests",
        {
            "number": 123,
            "title": "Connection failure",
            "body": None,
            "user": {"login": "reporter"},
            "labels": [{"name": "bug"}, {"name": "requests"}],
            "state": "open",
            "created_at": "2026-01-02T03:04:05Z",
            "updated_at": "2026-01-03T03:04:05Z",
            "html_url": "https://github.com/psf/requests/issues/123",
        },
        [{"user": {"login": "maintainer"}, "body": "Thanks", "created_at": "2026-01-04T03:04:05Z"}],
    )

    assert issue.repository == "psf/requests"
    assert issue.issue_number == 123
    assert issue.body == ""
    assert issue.labels == ["bug", "requests"]
    assert issue.comments[0].author == "maintainer"
    assert issue.created_at.year == 2026
