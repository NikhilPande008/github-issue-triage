from dataclasses import dataclass
from time import perf_counter
from typing import Callable, Protocol

from triage.domain.enums import Classification
from triage.github.models import GitHubIssue

MAX_BATCH_SIZE = 30
DEFAULT_BATCH_SIZE = 20


class IssueSelector(Protocol):
    def fetch_latest_open_issues(self, limit: int, start_page: int = 1) -> list[GitHubIssue]: ...


@dataclass(frozen=True)
class BatchItem:
    issue: GitHubIssue
    investigation_id: str | None
    classification: Classification | None
    duration_seconds: float | None
    cost_usd: float | None
    skipped: bool = False
    error: str | None = None


@dataclass(frozen=True)
class BatchSummary:
    items: list[BatchItem]

    def counts(self) -> dict[str, int]:
        result = {item.value: 0 for item in Classification if item is not Classification.DUPLICATE}
        result.update({"SKIPPED": 0, "OPERATIONAL_FAILURE": 0})
        for item in self.items:
            if item.skipped:
                result["SKIPPED"] += 1
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

    def run(self, repository: str, count: int = DEFAULT_BATCH_SIZE, start_page: int = 1, force: bool = False, progress: Callable[[str], None] | None = None) -> BatchSummary:
        if not 1 <= count <= MAX_BATCH_SIZE:
            raise ValueError(f"count must be between 1 and {MAX_BATCH_SIZE}")
        processed = set() if force else self.processed_numbers(repository)
        candidate_count = count if force else min(100, count + len(processed))
        items: list[BatchItem] = []
        processed_now = 0
        for issue in self.selector.fetch_latest_open_issues(candidate_count, start_page):
            if issue.issue_number in processed:
                item = BatchItem(issue, None, None, None, None, skipped=True)
                items.append(item)
                if progress: progress(f"#{issue.issue_number} SKIPPED (already processed)")
                continue
            if progress: progress(f"#{issue.issue_number} START {issue.title[:72]}")
            started = perf_counter()
            try:
                item = self.process(issue)
            except Exception as error:  # Continue the queue; the terminal retains the failure detail.
                item = BatchItem(issue, None, None, perf_counter() - started, None, error=str(error))
            items.append(item)
            processed_now += 1
            verdict = item.classification.value if item.classification else ("FAILED" if item.error else "UNKNOWN")
            if progress: progress(f"#{issue.issue_number} {verdict} ({(item.duration_seconds or 0):.1f}s)")
            if processed_now == count:
                break
        return BatchSummary(items)
