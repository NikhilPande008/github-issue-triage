from pathlib import Path
from time import monotonic

from triage.domain.models import InvestigationEvidence
from triage.investigation.models import AttemptExecution
from triage.sandbox.container import CodexExecutionResult, CodexSandboxUnavailable, SandboxTimeout
from triage.sandbox.manager import EnvironmentSetupFailure, SandboxManager


class DockerInvestigationRunner:
    """Runner-compatible, one-container-per-investigation execution backend."""

    def __init__(self, manager: SandboxManager, repository: str, pytest_timeout_seconds: int):
        self.manager = manager
        self.repository = repository
        self.pytest_timeout_seconds = pytest_timeout_seconds
        self.sandbox = None

    def __enter__(self) -> "DockerInvestigationRunner":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def run_attempt(self, repository_path: Path, prompt: str, artifact_dir: Path) -> AttemptExecution:
        run_id = artifact_dir.parent.name
        started = monotonic()
        if self.sandbox is None:
            try:
                self.sandbox = self.manager.create(run_id, self.repository)
            except EnvironmentSetupFailure as error:
                setup = error.setup
                terminal = "ENVIRONMENT SETUP FAILURE\n" + str(error) + "\n"
                if setup is not None:
                    terminal += f"Selected command: {setup.command}\nSelection reason: {setup.reason}\n"
                if error.output:
                    terminal += f"Setup output:\n{error.output}"
                error.execution = self._collect(
                    artifact_dir, terminal, "python -m pytest -q", "", "", 1, 1, started
                )
                raise
        codex_output = ""
        pytest_output = ""
        diff_output = ""
        codex_exit_code = 1
        pytest_exit_code = 1
        pytest_command = "python -m pytest -q"
        try:
            codex = self.sandbox.container.run_codex(prompt, self.manager.overall_timeout_seconds)
            codex_output, codex_exit_code = self._codex_log(codex), codex.result.exit_code
            changed = self.sandbox.container.run("git status --porcelain --untracked-files=all", self.pytest_timeout_seconds)
            pytest_command = _focused_pytest_command(changed.output)
            pytest = self.sandbox.container.run(pytest_command, self.pytest_timeout_seconds)
            pytest_output, pytest_exit_code = pytest.output, pytest.exit_code
            diff = self.sandbox.container.run("git diff --no-ext-diff", self.pytest_timeout_seconds)
            diff_output = diff.output
        except CodexSandboxUnavailable as error:
            codex_output = self._codex_log(
                CodexExecutionResult(error.fallback, error.preferred, error.fallback)
            )
            codex_output += f"CODEX SANDBOX ERROR: {error}\n"
            codex_exit_code = error.fallback.exit_code
        except SandboxTimeout as error:
            codex_output += f"\nTIMEOUT: {error}\n"
        return self._collect(artifact_dir, codex_output, pytest_command, pytest_output, diff_output, codex_exit_code, pytest_exit_code, started)

    def close(self) -> None:
        if self.sandbox is not None:
            self.sandbox.cleanup()
            self.sandbox = None

    def _collect(self, artifact_dir: Path, codex: str, pytest_command: str, pytest: str, diff: str, codex_exit_code: int, pytest_exit_code: int, started: float) -> AttemptExecution:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        container_dir = f"/sandbox-artifacts/{artifact_dir.name}"
        terminal = f"{codex}$ {pytest_command}\n{pytest}[exit {pytest_exit_code}]\n$ git diff --no-ext-diff\n{diff}"
        files = {"terminal.log": terminal, "pytest_output.txt": pytest, "git.diff": diff}
        for name, content in files.items():
            source = f"{container_dir}/{name}"
            destination = artifact_dir / name
            try:
                if self.sandbox is None:
                    raise RuntimeError("sandbox unavailable")
                self.sandbox.container.write_artifact(source, content)
                self.sandbox.container.copy_artifact(source, destination)
            except Exception:
                # A timeout can kill the container before its in-container artifact can be copied.
                destination.write_text(content, encoding="utf-8")
        return AttemptExecution(
            evidence=InvestigationEvidence(asserts_failure=False, git_diff_path=artifact_dir / "git.diff", pytest_output_path=artifact_dir / "pytest_output.txt", pytest_exit_code=pytest_exit_code),
            terminal_log_path=artifact_dir / "terminal.log",
            codex_exit_code=codex_exit_code,
            codex_latency_ms=round((monotonic() - started) * 1000),
        )

    @staticmethod
    def _codex_log(execution: CodexExecutionResult) -> str:
        records = [("preferred", execution.preferred)]
        if execution.fallback is not None:
            records.append(("Docker-isolated fallback", execution.fallback))
        return "".join(
            f"$ {result.command}\n{result.output}[exit {result.exit_code}; elapsed {result.elapsed_ms}ms; {label}]\n"
            for label, result in records
        )


def _focused_pytest_command(status_output: str) -> str:
    test_paths = []
    for line in status_output.splitlines():
        path = line[3:].split(" -> ")[-1]
        filename = Path(path).name
        if path.endswith(".py") and (path.startswith("tests/") or filename.startswith("test_")):
            test_paths.append(_shell_quote(path))
    if test_paths:
        return "python -m pytest -q " + " ".join(test_paths)
    return "python -m pytest -q"


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"
