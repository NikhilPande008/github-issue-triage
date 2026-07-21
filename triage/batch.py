from dataclasses import dataclass
from time import perf_counter
from typing import Callable, Protocol

from triage.domain.enums import Classification
from triage.github.models import GitHubIssue, GitHubIssuePage

MAX_BATCH_SIZE = 30
DEFAULT_BATCH_SIZE = 20
DEFAULT_MAX_SCAN_PAGES = 10


class IssueSelector(Protocol):
    def fetch_open_issue_page(self, page: int) -> GitHubIssuePage: ...


@dataclass(frozen=True)
class BatchItem:
    issue: GitHubIssue
    investigation_id: str | None
    classification: Classification | None
    duration_seconds: float | None
    cost_usd: float | None
    skipped: bool = False
    error: str | None = None
    job_status: str | None = None


@dataclass(frozen=True)
class BatchSummary:
    items: list[BatchItem]
    requested_count: int
    selected_count: int
    skipped_count: int
    pages_scanned: int
    selection_end: str

    def counts(self) -> dict[str, int]:
        result = {item.value: 0 for item in Classification if item is not Classification.DUPLICATE}
        result.update({"SKIPPED": 0, "OPERATIONAL_FAILURE": 0, "QUEUED": 0, "RUNNING": 0, "RETRIED": 0})
        for item in self.items:
            if item.skipped:
                result["SKIPPED"] += 1
            elif item.job_status:
                result[item.job_status] = result.get(item.job_status, 0) + 1
            elif item.error:
                result["OPERATIONAL_FAILURE"] += 1
            elif item.classification is not None:
                result[item.classification.value] += 1
        return result


class BatchTriageService:
    """Sequential, resumable orchestration around the normal per-issue pipeline."""

    def __init__(self, selector: IssueSelector, processed_numbers: Callable[[str], set[int]], process: Callable[[GitHubIssue], BatchItem]):
        self.selector = selector
        self.process = process
        self.processed_numbers = processed_numbers

    def run(
        self,
        repository: str,
        count: int = DEFAULT_BATCH_SIZE,
        start_page: int = 1,
        force: bool = False,
        progress: Callable[[str], None] | None = None,
        max_scan_pages: int = DEFAULT_MAX_SCAN_PAGES,
    ) -> BatchSummary:
        if not 1 <= count <= MAX_BATCH_SIZE:
            raise ValueError(f"count must be between 1 and {MAX_BATCH_SIZE}")
        if max_scan_pages < 1:
            raise ValueError("max_scan_pages must be at least 1")
        processed = set() if force else self.processed_numbers(repository)
        items: list[BatchItem] = []
        candidates: list[GitHubIssue] = []
        pages_scanned = 0
        selection_end = "scan-page limit reached"
        for page in range(start_page, start_page + max_scan_pages):
            issue_page = self.selector.fetch_open_issue_page(page)
            pages_scanned += 1
            for issue in issue_page.issues:
                if issue.issue_number in processed:
                    items.append(BatchItem(issue, None, None, None, None, skipped=True))
                    if progress:
                        progress(f"#{issue.issue_number} SKIPPED (already processed)")
                    continue
                candidates.append(issue)
                if len(candidates) == count:
                    selection_end = "requested count satisfied"
                    break
            if len(candidates) == count:
                break
            if issue_page.is_last_page:
                selection_end = "queue exhausted"
                break

        for issue in candidates:
            if progress: progress(f"#{issue.issue_number} START {issue.title[:72]}")
            started = perf_counter()
            try:
                item = self.process(issue)
            except Exception as error:  # Continue the queue; the terminal retains the failure detail.
                item = BatchItem(issue, None, None, perf_counter() - started, None, error=str(error))
            items.append(item)
            verdict = item.classification.value if item.classification else ("FAILED" if item.error else "UNKNOWN")
            if progress: progress(f"#{issue.issue_number} {verdict} ({(item.duration_seconds or 0):.1f}s)")
        return BatchSummary(
            items=items,
            requested_count=count,
            selected_count=len(candidates),
            skipped_count=sum(item.skipped for item in items),
            pages_scanned=pages_scanned,
            selection_end=selection_end,
        )
