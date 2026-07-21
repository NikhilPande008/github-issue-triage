import subprocess
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from triage.domain.models import InvestigationEvidence
from triage.investigation.models import AttemptExecution


@dataclass(frozen=True)
class CommandOutput:
    exit_code: int
    stdout: str
    stderr: str


def attempt_artifact_dir(artifacts_root: Path, run_id: str, attempt_number: int) -> Path:
    return artifacts_root / run_id / f"attempt_{attempt_number}"


class LocalInvestigationRunner:
    """Local command implementation of the engine's replaceable execution boundary."""

    def run_attempt(self, repository_path: Path, prompt: str, artifact_dir: Path) -> AttemptExecution:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        started = perf_counter()
        codex = self._run(["codex", "exec", "--sandbox", "workspace-write", "--ephemeral", prompt], repository_path)
        codex_latency_ms = round((perf_counter() - started) * 1000)
        structured_path = artifact_dir / "junit.xml"
        pytest = self._run(["python", "-m", "pytest", "-q", f"--junitxml={structured_path}"], repository_path)
        diff = self._run(["git", "diff", "--no-ext-diff"], repository_path)

        terminal_log_path = artifact_dir / "terminal.log"
        pytest_output_path = artifact_dir / "pytest_output.txt"
        git_diff_path = artifact_dir / "git.diff"
        terminal_log_path.write_text(
            self._terminal_log(codex, pytest, diff), encoding="utf-8"
        )
        pytest_output_path.write_text(pytest.stdout + pytest.stderr, encoding="utf-8")
        git_diff_path.write_text(diff.stdout + diff.stderr, encoding="utf-8")
        return AttemptExecution(
            evidence=InvestigationEvidence(
                asserts_failure=False,
                git_diff_path=git_diff_path,
                pytest_output_path=pytest_output_path,
                pytest_exit_code=pytest.exit_code,
                structured_results_path=structured_path if structured_path.is_file() else None,
            ),
            terminal_log_path=terminal_log_path,
            codex_exit_code=codex.exit_code,
            codex_latency_ms=codex_latency_ms,
        )

    @staticmethod
    def _run(command: list[str], repository_path: Path) -> CommandOutput:
        completed = subprocess.run(
            command,
            cwd=repository_path,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        return CommandOutput(completed.returncode, completed.stdout, completed.stderr)

    @staticmethod
    def _terminal_log(codex: CommandOutput, pytest: CommandOutput, diff: CommandOutput) -> str:
        return "".join(
            [
                "$ codex exec ...\n", codex.stdout, codex.stderr, f"[exit {codex.exit_code}]\n",
                "$ python -m pytest -q\n", pytest.stdout, pytest.stderr, f"[exit {pytest.exit_code}]\n",
                "$ git diff --no-ext-diff\n", diff.stdout, diff.stderr, f"[exit {diff.exit_code}]\n",
            ]
        )
