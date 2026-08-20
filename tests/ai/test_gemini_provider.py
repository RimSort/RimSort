from unittest.mock import patch

from app.ai.gemini_provider import GeminiProvider


def test_complete_on_tool_call_callback() -> None:
    provider = GeminiProvider("test-key", model="gemini-2.0-flash")
    traces: list[tuple[str, dict, dict]] = []

    def on_tool_call(name: str, args: dict, result: dict) -> None:
        traces.append((name, args, result))

    def fake_executor(name: str, args: dict) -> dict:
        return {"count": 2}

    tool_call_response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": "search_workshop_mods",
                                "args": {"query": "harmony russian"},
                            }
                        }
                    ]
                }
            }
        ]
    }
    text_response = {
        "candidates": [
            {"content": {"parts": [{"text": "Found mods."}]}}
        ]
    }

    with patch.object(provider, "_post", side_effect=[tool_call_response, text_response]):
        text = provider.complete(
            [{"role": "user", "content": "find russian mods"}],
            tools=[{"name": "search_workshop_mods"}],
            tool_executor=fake_executor,
            on_tool_call=on_tool_call,
        )

    assert text == "Found mods."
    assert len(traces) == 1
    assert traces[0][0] == "search_workshop_mods"
