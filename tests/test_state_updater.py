import config
from unittest.mock import MagicMock
from agent.state import new_state
from agent import state_updater

def _fake_reply(text: str):
    msg = MagicMock()
    msg.content = text
    resp = MagicMock()
    resp.choices = [MagicMock(message=msg)]
    return resp

def test_update_state_parses_and_merges(monkeypatch):
    reply = (
        '{"goal": "算1+2", "progress": ["已调用计算器"], '
        '"key_facts": ["结果是3"], "next_step": "回答用户"}'
    )
    monkeypatch.setattr(
        config.client.chat.completions, "create",
        lambda **kw: _fake_reply(reply),
    )
    out = state_updater.update_state(
        new_state(), [{"role": "tool", "name": "calculator", "content": "3"}]
    )
    assert out["progress"] == ["已调用计算器"]
    assert out["key_facts"] == ["结果是3"]
    assert out["next_step"] == "回答用户"
    assert out["status"] == "in_progress"   # status 不归更新器管

def test_update_state_strips_code_fence(monkeypatch):
    reply = '```json\n{"progress": ["步骤A"], "key_facts": [], "next_step": ""}\n```'
    monkeypatch.setattr(
        config.client.chat.completions, "create",
        lambda **kw: _fake_reply(reply),
    )
    out = state_updater.update_state(new_state(), [])
    assert out["progress"] == ["步骤A"]

def test_update_state_bad_json_keeps_old(monkeypatch):
    monkeypatch.setattr(
        config.client.chat.completions, "create",
        lambda **kw: _fake_reply("我不会输出JSON"),
    )
    old = new_state()
    old["goal"] = "保留我"
    assert state_updater.update_state(old, []) is old

def test_update_state_api_error_keeps_old(monkeypatch):
    def boom(**kw):
        raise RuntimeError("接口挂了")
    monkeypatch.setattr(config.client.chat.completions, "create", boom)
    assert state_updater.update_state(new_state(), []) is not None  # 旧 state 原样返回

def test_update_state_ignores_bad_types(monkeypatch):
    reply = '{"progress": "不是列表", "key_facts": [1, 2], "next_step": 3}'
    monkeypatch.setattr(
        config.client.chat.completions, "create",
        lambda **kw: _fake_reply(reply),
    )
    out = state_updater.update_state(new_state(), [])
    assert out["progress"] == []
    assert out["key_facts"] == []
    assert out["next_step"] == ""

def test_classify_new_task(monkeypatch):
    monkeypatch.setattr(
        config.client.chat.completions, "create",
        lambda **kw: _fake_reply('{"relation": "new_task", "new_goal": "写诗"}'),
    )
    v = state_updater.classify_turn(new_state(), [], "帮我写诗")
    assert v == {"relation": "new_task", "new_goal": "写诗"}


def test_classify_bad_output_defaults_continue(monkeypatch):
    monkeypatch.setattr(
        config.client.chat.completions, "create",
        lambda **kw: _fake_reply("看不懂的输出"),
    )
    assert state_updater.classify_turn(new_state(), [], "x")["relation"] == "continue"


def test_classify_api_error_defaults_continue(monkeypatch):
    def boom(**kw):
        raise RuntimeError("挂了")
    monkeypatch.setattr(config.client.chat.completions, "create", boom)
    assert state_updater.classify_turn(new_state(), [], "x")["relation"] == "continue"

