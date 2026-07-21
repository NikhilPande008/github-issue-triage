import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from triage.sandbox.manager import EnvironmentSetupFailure, SetupCommand


class RunnerSelectionError(EnvironmentSetupFailure):
    pass


class RunnerAdapter(Protocol):
    id: str
    output_artifact_kind: str
    def setup_command(self, repository_path: Path, configured_command: str | None) -> SetupCommand: ...
    def focused_command(self, status_output: str, structured_result_path: str | None = None) -> str: ...
    def is_test_path(self, path: Path) -> bool: ...
    def validate_output(self, output: str, exit_code: int): ...


def _quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


@dataclass(frozen=True)
class PytestAdapter:
    id: str = "pytest"
    output_artifact_kind: str = "pytest_output"

    def setup_command(self, repository_path: Path, configured_command: str | None) -> SetupCommand:
        if configured_command:
            return SetupCommand(configured_command, "explicit SANDBOX_SETUP_COMMAND")
        if (repository_path / "requirements-dev.txt").is_file():
            return SetupCommand("python -m pip install -r requirements-dev.txt", "requirements-dev.txt")
        if (repository_path / "requirements.txt").is_file():
            return SetupCommand("python -m pip install -r requirements.txt", "requirements.txt")
        for name in ("pyproject.toml", "setup.py", "setup.cfg"):
            if (repository_path / name).is_file():
                return SetupCommand("python -m pip install -e .", f"Python packaging metadata ({name})")
        raise EnvironmentSetupFailure("Environment setup unavailable for pytest: no supported Python dependency metadata found")

    def focused_command(self, status_output: str, structured_result_path: str | None = None) -> str:
        paths = _changed_paths(status_output, self.is_test_path)
        junit = f" --junitxml={_quote(structured_result_path)}" if structured_result_path else ""
        return "python -m pytest -q" + junit + (" " + " ".join(_quote(path) for path in paths) if paths else "")

    def is_test_path(self, path: Path) -> bool:
        return path.suffix == ".py" and (path.parts[0] == "tests" or path.name.startswith("test_"))

    def validate_output(self, output: str, exit_code: int):
        from triage.validation.pytest_parser import parse_pytest_output
        return parse_pytest_output(output, exit_code)


@dataclass(frozen=True)
class VitestAdapter:
    id: str = "vitest"
    output_artifact_kind: str = "vitest_output"

    def setup_command(self, repository_path: Path, configured_command: str | None) -> SetupCommand:
        if configured_command:
            return SetupCommand(configured_command, "explicit SANDBOX_SETUP_COMMAND")
        package = _package_json(repository_path)
        if package is None or not _has_vitest(package):
            raise EnvironmentSetupFailure("Environment setup unavailable for Vitest: package.json must declare vitest or set SANDBOX_SETUP_COMMAND")
        if (repository_path / "package-lock.json").is_file():
            return SetupCommand("npm ci", "package-lock.json with declared Vitest")
        # npm install is safe only for an explicitly declared Vitest project.
        return SetupCommand("npm install", "package.json with declared Vitest")

    def focused_command(self, status_output: str, structured_result_path: str | None = None) -> str:
        paths = _changed_paths(status_output, self.is_test_path)
        junit = f" --reporter=junit --outputFile={_quote(structured_result_path)}" if structured_result_path else ""
        return "npm exec -- vitest run" + junit + (" -- " + " ".join(_quote(path) for path in paths) if paths else "")

    def is_test_path(self, path: Path) -> bool:
        return path.suffix in {".js", ".jsx", ".ts", ".tsx"} and (
            path.parts[0] in {"test", "tests", "__tests__"} or ".test." in path.name or ".spec." in path.name
        )

    def validate_output(self, output: str, exit_code: int):
        from triage.validation.vitest_parser import parse_vitest_output
        return parse_vitest_output(output, exit_code)


def _changed_paths(status_output: str, predicate: Callable[[Path], bool]) -> list[str]:
    result: list[str] = []
    for line in status_output.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].split(" -> ")[-1]
        candidate = Path(path)
        if not candidate.is_absolute() and ".." not in candidate.parts and predicate(candidate):
            result.append(path)
    return result


def _package_json(path: Path) -> dict | None:
    try:
        data = json.loads((path / "package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _has_vitest(package: dict) -> bool:
    return "vitest" in package.get("devDependencies", {}) or "vitest" in package.get("dependencies", {})


def select_runner(configured: str, repository_path: Path | None = None) -> RunnerAdapter:
    adapters = {"pytest": PytestAdapter(), "vitest": VitestAdapter()}
    if configured in adapters:
        return adapters[configured]
    if configured != "auto":
        raise RunnerSelectionError(f"Unsupported test runner {configured!r}; supported runners are pytest and vitest")
    if repository_path is None:
        raise RunnerSelectionError("Automatic runner selection requires a repository path")
    candidates = []
    if any((repository_path / name).is_file() for name in ("requirements.txt", "requirements-dev.txt", "pyproject.toml", "setup.py", "setup.cfg")):
        candidates.append(adapters["pytest"])
    if _has_vitest(_package_json(repository_path) or {}):
        candidates.append(adapters["vitest"])
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise RunnerSelectionError("Unsupported repository: automatic selection found neither Python/pytest metadata nor a declared Vitest dependency")
    raise RunnerSelectionError("Ambiguous repository: automatic selection found both pytest and Vitest metadata; set TRIAGE_TEST_RUNNER explicitly")
