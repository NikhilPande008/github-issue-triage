from pathlib import Path
from time import monotonic
from datetime import datetime, timezone
from hashlib import sha256
import json

from triage.domain.models import InvestigationEvidence
from triage.investigation.models import AttemptExecution
from triage.sandbox.container import CodexExecutionResult, CodexSandboxUnavailable, SandboxTimeout
from triage.sandbox.manager import EnvironmentSetupFailure, SandboxManager
from triage.providers import CODEX_CAPABILITIES


class DockerInvestigationRunner:
    """Runner-compatible, one-container-per-investigation execution backend."""
    identifier = "codex"
    capabilities = CODEX_CAPABILITIES

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
        structured_container_path = f"/tmp/triage-{artifact_dir.parent.name}-{artifact_dir.name}-junit.xml"
        execution_failure_reason = None
        try:
            agent = getattr(self.sandbox, "agent_container", getattr(self.sandbox, "container", None))
            if agent is None:
                raise RuntimeError("agent container unavailable")
            codex = agent.run_codex(prompt, self.manager.overall_timeout_seconds)
            codex_output, codex_exit_code = self._codex_log(codex), codex.result.exit_code
            changed = agent.run("git status --porcelain --untracked-files=all", self.pytest_timeout_seconds)
            self._changed_status = changed.output
            if hasattr(self.manager, "close_agent_container"):
                self.manager.close_agent_container(self.sandbox)
            test_container = self._test_container()
            # Compatibility for lightweight test doubles; production sandboxes
            # receive their adapter during deterministic setup selection.
            runner_adapter = getattr(self.sandbox, "runner", None)
            if runner_adapter is None:
                from triage.runners.adapters import PytestAdapter
                runner_adapter = PytestAdapter()
            pytest_command = runner_adapter.focused_command(changed.output, structured_container_path)
            pytest = test_container.run(pytest_command, self.pytest_timeout_seconds)
            pytest_output, pytest_exit_code = pytest.output, pytest.exit_code
            diff = test_container.run("git diff --no-ext-diff", self.pytest_timeout_seconds)
            diff_output = diff.output
        except CodexSandboxUnavailable as error:
            codex_output = self._codex_log(
                CodexExecutionResult(error.fallback, error.preferred, error.fallback)
            )
            codex_output += f"CODEX SANDBOX ERROR: {error}\n"
            codex_exit_code = error.fallback.exit_code
        except SandboxTimeout as error:
            codex_output += f"\nTIMEOUT: {error}\n"
            execution_failure_reason = "Test execution timed out or crashed."
        return self._collect(artifact_dir, codex_output, pytest_command, pytest_output, diff_output, codex_exit_code, pytest_exit_code, started, structured_container_path, execution_failure_reason)

    def run_confirmation(self, repository_path: Path, prompt: str, artifact_dir: Path) -> AttemptExecution:
        """Re-run the identical focused test in the already prepared environment, without Codex."""
        if self.sandbox is None or not hasattr(self, "_changed_status"):
            return self.run_attempt(repository_path, prompt, artifact_dir)
        started = monotonic()
        runner = getattr(self.sandbox, "runner", None)
        if runner is None:
            from triage.runners.adapters import PytestAdapter
            runner = PytestAdapter()
        structured = f"/tmp/triage-{artifact_dir.parent.name}-{artifact_dir.name}-junit.xml"
        command = runner.focused_command(self._changed_status, structured)
        failure = None
        try:
            test_container = self._test_container()
            result = test_container.run(command, self.pytest_timeout_seconds)
            diff = test_container.run("git diff --no-ext-diff", self.pytest_timeout_seconds)
            return self._collect(artifact_dir, "CONFIRMATION EXECUTION (no Codex)\n", command, result.output, diff.output, 0, result.exit_code, started, structured)
        except SandboxTimeout:
            failure = "Test execution timed out or crashed."
            return self._collect(artifact_dir, "CONFIRMATION TIMEOUT\n", command, "", "", 0, 124, started, structured, failure)

    def close(self) -> None:
        if self.sandbox is not None:
            self.sandbox.cleanup()
            self.sandbox = None

    def _test_container(self):
        if hasattr(self.manager, "create_test_container"):
            return self.manager.create_test_container(self.sandbox)
        return getattr(self.sandbox, "test_container", None) or self.sandbox.container

    def _collect(self, artifact_dir: Path, codex: str, pytest_command: str, pytest: str, diff: str, codex_exit_code: int, pytest_exit_code: int, started: float, structured_container_path: str | None = None, execution_failure_reason: str | None = None) -> AttemptExecution:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        runner_id = getattr(getattr(self.sandbox, "runner", None), "id", "pytest")
        output_name = "pytest_output.txt" if runner_id == "pytest" else f"{runner_id}_output.txt"
        container_dir = f"/sandbox-artifacts/{artifact_dir.name}"
        terminal = f"{codex}$ {pytest_command}\n{pytest}[exit {pytest_exit_code}]\n$ git diff --no-ext-diff\n{diff}"
        files = {"terminal.log": terminal, output_name: pytest, "git.diff": diff}
        for name, content in files.items():
            source = f"{container_dir}/{name}"
            destination = artifact_dir / name
            try:
                if self.sandbox is None:
                    raise RuntimeError("sandbox unavailable")
                container = self._test_container()
                container.write_artifact(source, content)
                container.copy_artifact(source, destination)
            except Exception:
                # A timeout can kill the container before its in-container artifact can be copied.
                destination.write_text(content, encoding="utf-8")
        structured_path = artifact_dir / "junit.xml"
        if structured_container_path and self.sandbox is not None:
            try:
                self._test_container().copy_artifact(structured_container_path, structured_path)
            except Exception:
                # Absence is deliberate evidence: the validator rejects it.
                structured_path = None
        else:
            structured_path = None
        manifest_path = artifact_dir / "reproducibility_manifest.json"
        manifest = dict(getattr(self.sandbox, "manifest_base", None) or {})
        manifest.update({
            "investigation_agent_provider": self.identifier,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "focused_test_command": pytest_command,
            "runner_exit_code": pytest_exit_code,
            "execution_failure_reason": execution_failure_reason,
            "structured_results_path": str(structured_path) if structured_path else None,
            "artifacts": {
                name: {"path": str(artifact_dir / name), "sha256": sha256((artifact_dir / name).read_bytes()).hexdigest()}
                for name in ["terminal.log", output_name, "git.diff"] if (artifact_dir / name).is_file()
            },
        })
        if structured_path and structured_path.is_file():
            manifest["artifacts"]["junit.xml"] = {"path": str(structured_path), "sha256": sha256(structured_path.read_bytes()).hexdigest()}
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return AttemptExecution(
            evidence=InvestigationEvidence(asserts_failure=False, git_diff_path=artifact_dir / "git.diff", pytest_output_path=artifact_dir / output_name, pytest_exit_code=pytest_exit_code, runner_id=runner_id, structured_results_path=structured_path, execution_failure_reason=execution_failure_reason, reproducibility_manifest_path=manifest_path),
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
