from triage.extraction.prompts import load_system_prompt, render_user_prompt
from triage.github.models import GitHubIssue


def test_versioned_prompts_load_and_render_issue() -> None:
    issue = GitHubIssue(
        repository="psf/requests",
        issue_number=123,
        title="Failure",
        body="Only this text is available.",
        author="reporter",
        labels=[],
        comments=[],
        state="open",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        url="https://github.com/psf/requests/issues/123",
    )

    assert "Never infer" in load_system_prompt()
    assert "steps_to_reproduce" in load_system_prompt()
    rendered = render_user_prompt(issue)
    assert "{{issue_json}}" not in rendered
    assert '"issue_number": 123' in rendered
