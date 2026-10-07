from agent.state import new_state, normalize_state, new_task_state
from agent.memory import build_context

def test_new_state_is_independent():
    """测试 new_state() 每次返回的状态是否 \"互相独立\" """
    a, b = new_state(), new_state()
    a["progress"].append("x")
    assert b["progress"] == []          # 两份 state 不共享列表

# layer 层次|层级
def test_build_context_layers():
    """测试组装上下文"""
    recent = [
        {"role": "system", "content": "旧存档残留"},
        {"role": "user", "content": "你好"},
    ]
    ctx = build_context("基础规则", {"goal": "目标X"}, "", recent)
    assert ctx[0] == {"role": "system", "content": "基础规则"}
    assert "目标X" in ctx[1]["content"]
    assert ctx[2] == {"role": "user", "content": "你好"}
    assert len(ctx) == 3

def test_build_context_with_summary():
    """测试构建有记忆(memory)的上下文"""
    # ctx 是 context(上下文)的缩写
    ctx = build_context("基础规则", {"goal": "g"}, "早先算过结果是3", [])
    assert ctx[0]["content"] == "基础规则"
    assert ctx[1]["role"] == "system" and "结果是3" in ctx[1]["content"]
    assert ctx[2]["role"] == "system" # state 紧随其后

def test_normalize_fills_missing_keys():
    """测试规范化功能"""
    out = normalize_state({"goal": "g"})
    assert out["goal"] == "g"
    assert out["status"] == "in_progress"
    assert out["progress"] == [] and out["key_facts"] == []
    assert out["next_step"] == ""

def test_normalize_repairs_bad_types():
    out = normalize_state({"status": "wtf", "progress": "x", "key_facts": [1]})
    assert out["status"] == "in_progress"
    assert out["progress"] == [] and out["key_facts"] == []

def test_normalize_non_dict():
    assert normalize_state(None)["goal"] == ""
    assert normalize_state("坏了")["status"] == "in_progress"

def test_new_task_state():
    s = new_task_state("新目标")
    assert s["goal"] == "新目标"
    assert s["status"] == "in_progress"
    assert s["progress"] == []