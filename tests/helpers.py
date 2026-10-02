from unittest.mock import MagicMock

def make_tool_call(call_id: str, name: str, arguments: str):
    tc = MagicMock()
    tc.id = call_id
    tc.type = "function"
    tc.function.name = name
    tc.function.arguments = arguments      # JSON 字符串
    return tc

def _dump_tool_call(tc) -> dict:
    """把 mock 工具调用转成真实 SDK model_dump 的可序列化形状"""
    return {
        "id": tc.id,
        "type": "function",
        "function": {
            "name": tc.function.name,
            "arguments": tc.function.arguments,
        },
    }


def make_response(content="", tool_calls=None, reasoning=None):
    tool_calls = tool_calls or None

    # 同一份 message dump,同时用于 message.model_dump 和 response.model_dump
    message_dump = {
        "role": "assistant",
        "content": content,
        "tool_calls": (
            [_dump_tool_call(tc) for tc in tool_calls] if tool_calls else None
        ),
        "reasoning_content": reasoning,
    }

    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    msg.model_dump.return_value = message_dump

    resp = MagicMock()
    resp.choices = [MagicMock(message=msg)]
    resp.model_dump.return_value = {
        "choices": [{"message": message_dump}],
    }
    return resp


def fake_llm(responses: list):
    """每次调用按顺序吐出一个假响应"""
    queue = list(responses)

    def _create(**kwargs):
        return queue.pop(0)
    return _create
