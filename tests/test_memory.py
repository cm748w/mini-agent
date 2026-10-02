from agent.memory import needs_compaction, compact


def test_needs_compaction():
    assert needs_compaction([{"role": "user"}] * 6, threshold=5) # 阈值
    assert not needs_compaction([{"role": "user"}], threshold=5)


def test_compact_keeps_system():
    msgs = [{"role": "system", "content": "规则"}]
    msgs += [{"role": "user", "content": str(i)} for i in range(10)]
    out = compact(msgs, keep_recent=3)
    assert out[0]["role"] == "system"      # system 永远在
    assert len(out) == 4                    # 1 system + 3 recent


def test_compact_no_orphan_tool():
    msgs = [{"role": "system", "content": "规则"}]
    msgs += [
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "content": "结果", "tool_call_id": "c1"},
        {"role": "user", "content": "新问题"},
    ]
    out = compact(msgs, keep_recent=1)      # 切点可能落在 tool 上
    assert out[1]["role"] != "tool"         # 保留段不能以孤儿 tool 开头
