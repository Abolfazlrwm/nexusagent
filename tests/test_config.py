import pytest

from nexusagent.config import Settings


def test_defaults_with_no_environment_variables(monkeypatch):
    monkeypatch.delenv("NEXUS_ENV", raising=False)
    monkeypatch.delenv("NEXUS_LOG_LEVEL", raising=False)
    monkeypatch.delenv("NEXUS_MODEL", raising=False)
    monkeypatch.delenv("NEXUS_API_KEY", raising=False)
    monkeypatch.delenv("NEXUS_PROVIDER", raising=False)
    monkeypatch.delenv("NEXUS_ENDPOINT", raising=False)
    monkeypatch.delenv("NEXUS_TIMEOUT", raising=False)

    settings = Settings.from_env()

    assert settings.env == "development"
    assert settings.log_level == "INFO"
    assert settings.model is None
    assert settings.api_key is None
    assert settings.provider == "fake"
    assert settings.endpoint is None
    assert settings.timeout == 30.0


def test_environment_override(monkeypatch):
    monkeypatch.setenv("NEXUS_ENV", "production")

    settings = Settings.from_env()

    assert settings.env == "production"


def test_log_level_override(monkeypatch):
    monkeypatch.setenv("NEXUS_LOG_LEVEL", "DEBUG")

    settings = Settings.from_env()

    assert settings.log_level == "DEBUG"


def test_model_configured_through_environment(monkeypatch):
    monkeypatch.setenv("NEXUS_MODEL", "some-model-name")

    settings = Settings.from_env()

    assert settings.model == "some-model-name"


def test_api_key_read_from_environment(monkeypatch):
    monkeypatch.setenv("NEXUS_API_KEY", "test-placeholder-key")

    settings = Settings.from_env()

    assert settings.api_key == "test-placeholder-key"


def test_missing_api_key_does_not_fail(monkeypatch):
    monkeypatch.delenv("NEXUS_API_KEY", raising=False)

    settings = Settings.from_env()

    assert settings.api_key is None


def test_provider_configured_through_environment(monkeypatch):
    monkeypatch.setenv("NEXUS_PROVIDER", "openai")

    settings = Settings.from_env()

    assert settings.provider == "openai"


def test_endpoint_configured_through_environment(monkeypatch):
    monkeypatch.setenv("NEXUS_ENDPOINT", "https://example.test/generate")

    settings = Settings.from_env()

    assert settings.endpoint == "https://example.test/generate"


def test_timeout_configured_through_environment(monkeypatch):
    monkeypatch.setenv("NEXUS_TIMEOUT", "5")

    settings = Settings.from_env()

    assert settings.timeout == 5.0


def test_settings_is_immutable():
    settings = Settings.from_env()

    with pytest.raises(AttributeError):
        settings.env = "changed"


def test_repr_does_not_expose_api_key(monkeypatch):
    monkeypatch.setenv("NEXUS_API_KEY", "super-secret-value")

    settings = Settings.from_env()

    assert "super-secret-value" not in repr(settings)
    assert "set" in repr(settings)
