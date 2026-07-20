from triage.config.settings import Settings


def test_settings_load_environment(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("GITHUB_TOKEN", "github-token")
    monkeypatch.setenv("DEMO_REPOSITORY", "example/repository")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LOCAL_REPOSITORY_PATH", "/tmp/requests")

    settings = Settings(_env_file=None)

    assert settings.openai_api_key == "test-key"
    assert settings.github_token == "github-token"
    assert settings.demo_repository == "example/repository"
    assert settings.database_url == "sqlite:///test.db"
    assert settings.log_level == "DEBUG"
    assert str(settings.local_repository_path) == "/tmp/requests"


def test_settings_default_repository() -> None:
    settings = Settings(_env_file=None)
    assert settings.demo_repository == "psf/requests"
    assert settings.github_token is None
