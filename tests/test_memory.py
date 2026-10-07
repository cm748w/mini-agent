from agent.memory import (
    needs_compaction, compact, truncate_by_tokens,
    estimate_tokens, over_token_limit, trim_recent_by_tokens,
)

def test_needs_compaction():
    """测试裁剪判定是否正常"""
    assert needs_compaction([{"role": "user"}] * 6, threshold=5) # 阈值
    assert not needs_compaction([{"role": "user"}], threshold=5)

def test_compact_keeps_system():
    """测试裁剪后是否可以正常保留系统(system)提示词"""
    msgs = [{"role": "system", "content": "规则"}]
    msgs += [{"role": "user", "content": str(i)} for i in range(10)]
    out = compact(msgs, keep_recent=3)
    assert out[0]["role"] == "system"      # system 永远在
    assert len(out) == 4                    # 1 system + 3 recent

def test_compact_no_orphan_tool():
    """测试裁剪完后是否会出现tool开头的情况"""
    msgs = [{"role": "system", "content": "规则"}]
    msgs += [
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "content": "结果", "tool_call_id": "c1"},
        {"role": "user", "content": "新问题"},
    ]
    out = compact(msgs, keep_recent=1)      # 切点可能落在 tool 上
    assert out[1]["role"] != "tool"         # 保留段不能以孤儿 tool 开头

def test_estimate_tokens_wide_vs_narrow():
    """测试 **token估算** 是否准确"""
    assert estimate_tokens("你好世界") == 4   # 4 个全角字
    assert estimate_tokens("abcd") == 1       # 4 个半角字符 // 4

def test_over_token_limit():
    """测试 **token超限** 方法是否准确"""
    msg = {"role": "user", "content": "你好世界"}
    assert over_token_limit([msg], token_limit=1)
    assert not over_token_limit([msg], token_limit=10_000)

def test_trim_keeps_latest_and_no_orphan_tool():
    """测试 **裁剪功能** 是否正常"""
    msgs = [
        {"role": "user", "content": "很早的问题"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "calculator", "arguments": "{}"}}]},
        {"role": "tool", "content": "3", "tool_call_id": "c1", "name": "calculator"},
        {"role": "user", "content": "最新问题"},
    ]
    kept, dropped = trim_recent_by_tokens(msgs, keep_tokens=1)
    assert kept == [{"role": "user", "content": "最新问题"}]
    assert kept[0]["role"] != "tool"
    assert dropped[0]["content"] == "很早的问题"

def test_truncate_by_tokens():
    """测试 超 token 的情况"""
    out = truncate_by_tokens("你好世界" * 100, token_limit=10)
    assert out == "你好世界" * 2 + "你好"
    assert len(out) == 10

def test_truncate_short_test_untouched():
    """测试 不超 token 的情况"""
    assert truncate_by_tokens("你好", 100) =="你好"

