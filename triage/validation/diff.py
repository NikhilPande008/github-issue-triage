from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiffAnalysis:
    changed_test_paths: list[Path]


def analyze_diff(content: str) -> DiffAnalysis:
    changed: list[Path] = []
    current_path: Path | None = None
    additions: list[str] = []
    removals: list[str] = []

    def finish_file() -> None:
        if current_path is not None and _is_test_path(current_path) and _has_executable_change(additions, removals):
            changed.append(current_path)

    for line in content.splitlines():
        if line.startswith("diff --git "):
            finish_file()
            additions, removals = [], []
            parts = line.split()
            current_path = Path(parts[3][2:]) if len(parts) >= 4 and parts[3].startswith("b/") else None
        elif line.startswith("+++ "):
            if line == "+++ /dev/null":
                current_path = None
        elif line.startswith("+") and not line.startswith("+++"):
            additions.append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            removals.append(line[1:])
    finish_file()
    return DiffAnalysis(changed_test_paths=changed)


def _is_test_path(path: Path) -> bool:
    return path.suffix == ".py" and (path.parts[0] == "tests" or path.name.startswith("test_"))


def _has_executable_change(additions: list[str], removals: list[str]) -> bool:
    added = [_normalize(line) for line in additions if _normalize(line)]
    removed = [_normalize(line) for line in removals if _normalize(line)]
    return Counter(added) != Counter(removed)


def _normalize(line: str) -> str:
    code = line.split("#", maxsplit=1)[0]
    return "".join(code.split())
