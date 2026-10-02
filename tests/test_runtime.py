import pytest
import config
from agent.session import SessionManager
from agent.trace import Trace
from agent import agent_run
from tests.helpers import fake_llm, make_response, make_tool_call


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    """隔离存储和 trace 文件,返回一个干净的 SessionManager"""
    monkeypatch.setattr(config, "SESSIONS_FILE", str(tmp_path / "sessions.json"))
    monkeypatch.setattr(Trace, "save", lambda self, path: None)
    return SessionManager()


def test_path_direct_answer(isolated, monkeypatch):
    """路径1: 模型不调工具,直接回答"""
    monkeypatch.setattr(
        config.client.chat.completions, "create",
        fake_llm([make_response(content="你好,我是助手")]),
    )
    s = isolated.create()
    assert agent_run("你好", s, isolated) == "你好,我是助手"


def test_path_tool_loop(isolated, monkeypatch):
    """路径2: 第一轮调工具,第二轮根据结果给出答案"""
    tc = make_tool_call("c1", "calculator",
                        '{"a": 1, "b": 2, "operator": "+"}')
    monkeypatch.setattr(
        config.client.chat.completions, "create",
        fake_llm([
            make_response(tool_calls=[tc]),
            make_response(content="答案是 3"),
        ]),
    )
    s = isolated.create()
    assert agent_run("算 1+2", s, isolated) == "答案是 3"

    tool_msgs = [m for m in s.messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["content"] == "3"


def test_path_tool_error_recovery(isolated, monkeypatch):
    """路径3: 工具抛错 → 错误回喂 → 模型如实说明"""
    tc = make_tool_call("c1", "calculator",
                        '{"a": "苹果", "b": 2, "operator": "+"}')
    monkeypatch.setattr(
        config.client.chat.completions, "create",
        fake_llm([
            make_response(tool_calls=[tc]),
            make_response(content="苹果不是数字,无法计算"),
        ]),
    )
    s = isolated.create()
    result = agent_run("苹果加 2", s, isolated)

    assert "不是数字" in result
    tool_msgs = [m for m in s.messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert "TypeError" in tool_msgs[0]["content"]


def test_path_max_rounds(isolated, monkeypatch):
    """路径4: 模型持续要求调工具,达到 MAX_ROUNDS 后强制结束"""
    counter = {"n": 0}

    def always_tools(**kwargs):
        counter["n"] += 1
        return make_response(tool_calls=[
            make_tool_call(f"c{counter['n']}", "get_current_time", "{}")
        ])

    monkeypatch.setattr(config.client.chat.completions, "create", always_tools)
    s = isolated.create()
    result = agent_run("无限循环测试", s, isolated)

    assert "最大轮次" in result
    assert counter["n"] == config.MAX_ROUNDS
