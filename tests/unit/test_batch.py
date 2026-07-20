from triage.batch import BatchItem, BatchTriageService
from triage.domain.enums import Classification
from triage.github.models import GitHubIssue


def issue(number: int) -> GitHubIssue:
    return GitHubIssue(
        repository="psf/requests", issue_number=number, title=f"Issue {number}", body="", author="reporter",
        labels=[], comments=[], state="open", created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z", url=f"https://github.com/psf/requests/issues/{number}",
    )


class Selector:
    def __init__(self, issues: list[GitHubIssue]):
        self.issues = issues
        self.calls: list[tuple[int, int]] = []

    def fetch_latest_open_issues(self, limit: int, start_page: int = 1) -> list[GitHubIssue]:
        self.calls.append((limit, start_page))
        return self.issues[:limit]


def test_batch_processes_open_issues_sequentially_and_aggregates_results() -> None:
    selector = Selector([issue(3), issue(2), issue(1)])
    order: list[int] = []

    def process(item: GitHubIssue) -> BatchItem:
        order.append(item.issue_number)
        verdict = Classification.REPRODUCED if item.issue_number == 3 else Classification.WONT_REPRO
        return BatchItem(item, f"run-{item.issue_number}", verdict, 1.0, None)

    summary = BatchTriageService(selector, lambda repository: set(), process).run("psf/requests", count=3, start_page=2)

    assert selector.calls == [(3, 2)]
    assert order == [3, 2, 1]
    assert summary.counts() == {"REPRODUCED": 1, "NEEDS_INFO": 0, "WONT_REPRO": 2, "NOT_A_BUG": 0, "SKIPPED": 0, "OPERATIONAL_FAILURE": 0}


def test_batch_skips_processed_issues_and_continues_after_operational_failure() -> None:
    selector = Selector([issue(3), issue(2), issue(1)])
    processed: list[int] = []

    def process(item: GitHubIssue) -> BatchItem:
        processed.append(item.issue_number)
        if item.issue_number == 2:
            raise RuntimeError("Docker unavailable")
        return BatchItem(item, "run-1", Classification.NEEDS_INFO, 1.0, None)

    summary = BatchTriageService(selector, lambda repository: {3}, process).run("psf/requests", count=3)

    assert selector.calls == [(4, 1)]
    assert processed == [2, 1]
    assert summary.items[0].skipped is True
    assert summary.items[1].error == "Docker unavailable"
    assert summary.counts()["SKIPPED"] == 1
    assert summary.counts()["OPERATIONAL_FAILURE"] == 1


def test_batch_force_reprocesses_existing_issue() -> None:
    selected = Selector([issue(3)])
    summary = BatchTriageService(selected, lambda repository: {3}, lambda item: BatchItem(item, "run-3", Classification.NOT_A_BUG, 1, None)).run("psf/requests", 1, force=True)
    assert summary.items[0].skipped is False


def test_batch_preserves_attributable_cost_from_each_processed_investigation() -> None:
    selector = Selector([issue(2), issue(1)])
    costs = {2: 0.004184, 1: 0.003070}

    summary = BatchTriageService(
        selector,
        lambda repository: set(),
        lambda item: BatchItem(item, f"run-{item.issue_number}", Classification.NEEDS_INFO, 1, costs[item.issue_number]),
    ).run("psf/requests", count=2)

    assert [item.cost_usd for item in summary.items] == [0.004184, 0.003070]
