"""Claude Code CLI investigation adapter; no fallback to Codex."""
from __future__ import annotations
import shutil
from pathlib import Path
from time import monotonic
from triage.providers import ProviderCapabilities
from triage.sandbox.manager import EnvironmentSetupFailure
from triage.sandbox.runner import DockerInvestigationRunner

CLAUDE_CAPABILITIES=ProviderCapabilities(False,False,False,False,True,False)
class ClaudeCodeInvestigationAgentProvider(DockerInvestigationRunner):
    identifier="claude_code"; capabilities=CLAUDE_CAPABILITIES
    def __init__(self,manager,repository,pytest_timeout_seconds,command:str,model:str|None=None):
        super().__init__(manager,repository,pytest_timeout_seconds);self.command=command;self.model=model or "unknown"
    def validate(self)->None:
        if not self.command.strip():raise ValueError("CLAUDE_CODE_COMMAND is required when investigation-agent provider is claude_code")
        if self.manager.network_policy!="allowed":raise ValueError("claude_code requires TRIAGE_TEST_NETWORK_POLICY=allowed; isolated execution cannot reach its configured credential surface")
    def run_attempt(self,repository_path:Path,prompt:str,artifact_dir:Path):
        self.validate();run_id=artifact_dir.parent.name;started=monotonic()
        if self.sandbox is None:self.sandbox=self.manager.create(run_id,self.repository)
        # Claude Code connectivity is confined to the provider invocation; the
        # subsequent focused test still uses the configured sandbox policy.
        escaped=prompt.replace("'","'\"'\"'"); result=self.sandbox.container.run(f"{self.command} -p '{escaped}'",self.manager.overall_timeout_seconds)
        changed=self.sandbox.container.run("git status --porcelain --untracked-files=all",self.pytest_timeout_seconds);self._changed_status=changed.output
        runner=getattr(self.sandbox,"runner",None)
        if runner is None:
            from triage.runners.adapters import PytestAdapter
            runner=PytestAdapter()
        structured=f"/tmp/triage-{artifact_dir.parent.name}-{artifact_dir.name}-junit.xml"; command=runner.focused_command(changed.output,structured); pytest=self.sandbox.container.run(command,self.pytest_timeout_seconds);diff=self.sandbox.container.run("git diff --no-ext-diff",self.pytest_timeout_seconds)
        return self._collect(artifact_dir,f"$ {self.command} -p …\n{result.output}[exit {result.exit_code}]\n",command,pytest.output,diff.output,result.exit_code,pytest.exit_code,started,structured)
