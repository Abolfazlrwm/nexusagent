import pytest

from nexusagent.provider import Message, Provider, TextResponse, ToolCallRequest, last_user_text
from nexusagent.providers import FakeProvider


def test_message_roles_validated():
    with pytest.raises(ValueError):
        Message("robot", "x")


def test_message_content_must_be_string():
    with pytest.raises(TypeError):
        Message("user", 5)


def test_tool_message_requires_tool_call():
    with pytest.raises(ValueError):
        Message("tool", "result")


def test_user_message_cannot_carry_tool_call():
    with pytest.raises(ValueError):
        Message("user", "x", tool_call=ToolCallRequest("echo", "x"))


def test_message_is_immutable():
    with pytest.raises(AttributeError):
        Message("user", "x").content = "y"


def test_tool_call_request_call_id_defaults_to_none():
    assert ToolCallRequest("echo", "x").call_id is None


def test_last_user_text_picks_most_recent_user_message():
    messages = [Message("user", "a"), Message("assistant", "b"), Message("user", "c")]
    assert last_user_text(messages) == "c"


def test_last_user_text_requires_a_user_message():
    with pytest.raises(ValueError):
        last_user_text([Message("assistant", "b")])


def test_default_respond_delegates_to_generate():
    response = FakeProvider().respond([Message("user", "hello")])
    assert response == TextResponse("fake response: hello")


def test_custom_provider_only_needs_generate():
    class P(Provider):
        def generate(self, prompt):
            return prompt.upper()

    assert P().respond([Message("user", "a")]) == TextResponse("A")
