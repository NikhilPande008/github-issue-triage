from contextlib import nullcontext

import triage.cli as cli
from triage.config.settings import Settings
from triage.investigation.runner import LocalInvestigationRunner


def test_local_runner_is_available_only_by_configuration() -> None:
    context = cli._runner_context(Settings(investigation_runner="local", _env_file=None))
    with context as runner:
        assert isinstance(runner, LocalInvestigationRunner)


def test_docker_runner_is_default(monkeypatch) -> None:
    class FakeRunner:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    monkeypatch.setattr(cli, "SandboxManager", lambda **kwargs: object())
    monkeypatch.setattr(cli, "DockerInvestigationRunner", lambda *args: FakeRunner())
    context = cli._runner_context(Settings(_env_file=None))
    with context as runner:
        assert isinstance(runner, FakeRunner)
