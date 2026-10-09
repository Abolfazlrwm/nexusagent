"""Whole stack: Settings -> Runtime -> Agent loop -> provider over (mocked) HTTP."""

import json
from unittest.mock import MagicMock, patch

from nexusagent import Settings, create_application_runtime

URLOPEN = "nexusagent.http_provider.urllib.request.urlopen"


def reply(payload):
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode()
    response.__enter__.return_value = response
    return response


@patch(URLOPEN)
def test_generic_http_backend_drives_a_tool_loop(mock):
    mock.side_effect = [
        reply({"tool_name": "calculator", "tool_input": "20 / 4"}),
        reply({"output": "It is 5."}),
    ]
    runtime = create_application_runtime(Settings(provider="http", endpoint="https://x.test/"))

    result = runtime.run("what is 20 / 4?")

    assert (result.success, result.output) == (True, "It is 5.")
    assert result.steps[0].tool_output == "5"
    second_body = json.loads(mock.call_args_list[1].args[0].data)
    assert second_body["messages"][-1]["role"] == "tool"
    assert second_body["messages"][-1]["content"] == "5"


@patch(URLOPEN)
def test_openai_backend_loop_and_conversation(mock):
    def tool_call():
        return reply(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "t1",
                                    "function": {
                                        "name": "uppercase",
                                        "arguments": '{"input": "abc"}',
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        )

    def text(t):
        return reply({"choices": [{"message": {"content": t}}]})

    mock.side_effect = [tool_call(), text("ABC!"), text("Sure.")]
    runtime = create_application_runtime(Settings(provider="openai", model="m", api_key="k"))
    chat = runtime.conversation()

    first = chat.send("shout abc")
    chat.send("thanks")

    assert first.output == "ABC!"
    third_body = json.loads(mock.call_args_list[2].args[0].data)
    roles = [m["role"] for m in third_body["messages"]]
    assert roles == ["user", "assistant", "tool", "assistant", "user"]


def test_default_fake_runtime_behaviour_is_unchanged():
    result = create_application_runtime().run("Hello NexusAgent")

    assert result.output == "fake response: Hello NexusAgent"
    assert result.steps == ()
