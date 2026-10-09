import pytest

from nexusagent.config import Settings


def test_defaults():
    s = Settings()
    assert s.system_prompt is None
    assert s.max_steps == 8


def test_from_env_reads_new_variables(monkeypatch):
    monkeypatch.setenv("NEXUS_SYSTEM_PROMPT", "Be nice.")
    monkeypatch.setenv("NEXUS_MAX_STEPS", "3")

    s = Settings.from_env()

    assert (s.system_prompt, s.max_steps) == ("Be nice.", 3)


def test_repr_does_not_print_system_prompt():
    assert "Be nice." not in repr(Settings(system_prompt="Be nice."))


@pytest.mark.parametrize("bad", [0, -2, 101, True, 2.5])
def test_invalid_max_steps(bad):
    with pytest.raises(ValueError, match="max_steps"):
        Settings(max_steps=bad).validate()


def test_blank_system_prompt_rejected():
    with pytest.raises(ValueError, match="System prompt"):
        Settings(system_prompt=" ").validate()


def test_openai_requires_model_but_not_key_or_endpoint():
    with pytest.raises(ValueError, match="model"):
        Settings(provider="openai").validate()
    Settings(provider="openai", model="m").validate()  # local servers need no key


def test_anthropic_requires_model_and_key():
    with pytest.raises(ValueError, match="model"):
        Settings(provider="anthropic", api_key="k").validate()
    with pytest.raises(ValueError, match="API key"):
        Settings(provider="anthropic", model="m").validate()
    Settings(provider="anthropic", model="m", api_key="k").validate()


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_custom_endpoint_must_be_http(provider):
    with pytest.raises(ValueError, match="http or https"):
        Settings(provider=provider, model="m", api_key="k", endpoint="ftp://x").validate()
