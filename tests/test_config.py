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


def test_validate_accepts_default_fake_settings():
    Settings().validate()


def test_validate_accepts_valid_http_settings():
    Settings(
        provider="http",
        endpoint="https://example.test/generate",
        timeout=10,
    ).validate()


def test_validate_accepts_http_without_api_key():
    Settings(
        provider="http",
        endpoint="https://example.test/generate",
        api_key=None,
    ).validate()


def test_validate_rejects_unsupported_provider():
    with pytest.raises(ValueError, match="something"):
        Settings(provider="something").validate()


def test_validate_rejects_empty_model():
    with pytest.raises(ValueError):
        Settings(model="").validate()


def test_validate_rejects_whitespace_only_model():
    with pytest.raises(ValueError):
        Settings(model="   ").validate()


def test_validate_accepts_valid_model():
    Settings(model="a-real-model").validate()


def test_validate_accepts_missing_model():
    Settings(model=None).validate()


def test_validate_rejects_missing_endpoint_for_http():
    with pytest.raises(ValueError):
        Settings(provider="http", endpoint=None).validate()


def test_validate_rejects_empty_endpoint_for_http():
    with pytest.raises(ValueError):
        Settings(provider="http", endpoint="").validate()


def test_validate_rejects_whitespace_only_endpoint_for_http():
    with pytest.raises(ValueError):
        Settings(provider="http", endpoint="   ").validate()


def test_validate_accepts_http_endpoint():
    Settings(provider="http", endpoint="http://example.test/generate").validate()


def test_validate_accepts_https_endpoint():
    Settings(provider="http", endpoint="https://example.test/generate").validate()


@pytest.mark.parametrize(
    "endpoint",
    ["ftp://example.test", "file:///etc/passwd", "abc://example.test", "example.test"],
)
def test_validate_rejects_unsupported_endpoint_scheme(endpoint):
    with pytest.raises(ValueError):
        Settings(provider="http", endpoint=endpoint).validate()


@pytest.mark.parametrize("timeout", [0, -1])
def test_validate_rejects_non_positive_timeout(timeout):
    with pytest.raises(ValueError):
        Settings(timeout=timeout).validate()


def test_validate_rejects_nan_timeout():
    with pytest.raises(ValueError):
        Settings(timeout=float("nan")).validate()


def test_validate_rejects_positive_infinity_timeout():
    with pytest.raises(ValueError):
        Settings(timeout=float("inf")).validate()


def test_validate_rejects_negative_infinity_timeout():
    with pytest.raises(ValueError):
        Settings(timeout=float("-inf")).validate()


def test_validate_accepts_positive_finite_timeout():
    Settings(timeout=15.5).validate()


def test_validate_error_does_not_leak_api_key():
    settings = Settings(provider="something", api_key="super-secret-value")

    with pytest.raises(ValueError) as exc_info:
        settings.validate()

    assert "super-secret-value" not in str(exc_info.value)


def test_validate_does_not_perform_network_access(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Settings.validate() must not perform network access")

    monkeypatch.setattr("socket.socket.connect", fail_if_called)

    Settings(provider="http", endpoint="https://example.test/generate").validate()
