import pytest

from triage.batch import BatchItem, BatchTriageService
from triage.domain.enums import Classification
from triage.github.client import GitHubRateLimitError
from triage.github.models import GitHubIssue, GitHubIssuePage


def issue(number: int) -> GitHubIssue:
    return GitHubIssue(
        repository="psf/requests", issue_number=number, title=f"Issue {number}", body="", author="reporter",
        labels=[], comments=[], state="open", created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z", url=f"https://github.com/psf/requests/issues/{number}",
    )


class Selector:
    def __init__(self, pages: list[GitHubIssuePage]):
        self.pages = pages
        self.calls: list[int] = []

    def fetch_open_issue_page(self, page: int) -> GitHubIssuePage:
        self.calls.append(page)
        return self.pages[page - 1] if page <= len(self.pages) else GitHubIssuePage(issues=[], is_last_page=True)


def page(numbers: list[int], is_last_page: bool = False) -> GitHubIssuePage:
    return GitHubIssuePage(issues=[issue(number) for number in numbers], is_last_page=is_last_page)


def test_batch_scans_later_pages_to_find_requested_new_issues_after_many_processed() -> None:
    selector = Selector([page(list(range(300, 200, -1))), page([200, 199, 198], is_last_page=True)])
    processed = set(range(203, 301))
    processed_order: list[int] = []

    def process(item: GitHubIssue) -> BatchItem:
        processed_order.append(item.issue_number)
        return BatchItem(item, f"run-{item.issue_number}", Classification.NEEDS_INFO, 1.0, None)

    summary = BatchTriageService(selector, lambda repository: processed, process).run("psf/requests", count=3)

    assert selector.calls == [1, 2]
    assert processed_order == [202, 201, 200]
    assert summary.selected_count == 3
    assert summary.skipped_count == 98
    assert summary.pages_scanned == 2
    assert summary.selection_end == "requested count satisfied"


def test_batch_stops_pagination_as_soon_as_requested_candidates_are_found() -> None:
    selector = Selector([page([3, 2, 1]), page([0], is_last_page=True)])
    summary = BatchTriageService(
        selector, lambda repository: set(), lambda item: BatchItem(item, "run", Classification.BEHAVIOR_GAP_CONFIRMED, 1, None)
    ).run("psf/requests", count=2)

    assert selector.calls == [1]
    assert summary.selected_count == 2


def test_pr_heavy_pages_do_not_reduce_requested_new_issue_count() -> None:
    # A service page with no issues but not marked last represents a GitHub page containing only PRs.
    selector = Selector([page([]), page([5, 4], is_last_page=True)])
    processed: list[int] = []
    summary = BatchTriageService(
        selector,
        lambda repository: set(),
        lambda item: processed.append(item.issue_number) or BatchItem(item, "run", Classification.NEEDS_INFO, 1, None),
    ).run("psf/requests", count=2)

    assert selector.calls == [1, 2]
    assert processed == [5, 4]
    assert summary.selected_count == 2


def test_batch_start_page_begins_scanning_at_requested_github_page() -> None:
    selector = Selector([page([99]), page([88]), page([77], is_last_page=True)])
    summary = BatchTriageService(
        selector, lambda repository: set(), lambda item: BatchItem(item, "run", Classification.NOT_A_BUG, 1, None)
    ).run("psf/requests", count=1, start_page=3)

    assert selector.calls == [3]
    assert summary.items[0].issue.issue_number == 77


def test_exhausted_queue_reports_explicit_shortfall_metadata() -> None:
    selector = Selector([page([2], is_last_page=True)])
    summary = BatchTriageService(
        selector, lambda repository: set(), lambda item: BatchItem(item, "run", Classification.NEEDS_INFO, 1, None)
    ).run("psf/requests", count=5)

    assert summary.selected_count == 1
    assert summary.pages_scanned == 1
    assert summary.selection_end == "queue exhausted"


def test_scan_page_limit_is_distinct_from_queue_exhaustion() -> None:
    selector = Selector([page([3]), page([2]), page([1], is_last_page=True)])
    summary = BatchTriageService(
        selector, lambda repository: set(), lambda item: BatchItem(item, "run", Classification.NEEDS_INFO, 1, None)
    ).run("psf/requests", count=3, max_scan_pages=2)

    assert selector.calls == [1, 2]
    assert summary.selected_count == 2
    assert summary.selection_end == "scan-page limit reached"


def test_batch_force_reprocesses_existing_issues() -> None:
    selector = Selector([page([3], is_last_page=True)])
    summary = BatchTriageService(
        selector, lambda repository: {3}, lambda item: BatchItem(item, "run-3", Classification.NOT_A_BUG, 1, None)
    ).run("psf/requests", 1, force=True)
    assert summary.items[0].skipped is False


def test_rate_limited_candidate_fetch_stops_before_any_investigation_or_runner_starts() -> None:
    class RateLimitedSelector:
        def fetch_open_issue_page(self, page: int):
            raise GitHubRateLimitError("GitHub API rate limit exhausted.")

    started: list[int] = []
    service = BatchTriageService(
        RateLimitedSelector(),
        lambda repository: set(),
        lambda item: started.append(item.issue_number),
    )
    with pytest.raises(GitHubRateLimitError):
        service.run("psf/requests", count=5)
    assert started == []
