import pytest
import config
from agent.session import SessionManager
from agent.trace import Trace
from agent.runtime import agent_run
from tests.helpers import fake_llm, make_response, make_tool_call


@pytest.fixture
def isolated(monkeypatch, tmp_path): # isolated —— 隔离的
    """隔离存储和 trace 文件,返回一个干净的 SessionManager"""
    monkeypatch.setattr(config, "SESSIONS_FILE", str(tmp_path / "sessions.json"))
    monkeypatch.setattr(Trace, "save", lambda self, path: None)
    # 主流程测试不关心 State 更新: 直接沿用旧 state, 避免多吃 fake_llm 队列的响应
    monkeypatch.setattr(
        "agent.runtime.update_state",
        lambda old_state, events: old_state
    )
    monkeypatch.setattr(
        "agent.runtime.classify_turn",
        lambda state, recent, msg: {"relation": "continue", "new_goal": ""}
    )
    monkeypatch.setattr(
        "agent.runtime.summarize",
        lambda old_summary, dropped: old_summary
    )
    monkeypatch.setattr(
        "agent.runtime.summarize",
        lambda old_summary, dropped, archive_path="": old_summary
    )

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

def test_state_rollover_on_new_task(isolated, monkeypatch):
    """上一任务 done 后判定为新任务 -> state 以新目标轮转"""
    monkeypatch.setattr(
        "agent.runtime.classify_turn",
        lambda state, recent, msg: {"relation": "new_task", "new_goal": "写一首诗"},
    )
    monkeypatch.setattr(
        config.client.chat.completions, "create",
        fake_llm([make_response(content="好的,这是诗...")]),
    )
    s = isolated.create()
    s.state["goal"] = "旧任务"
    s.state["status"] = "done"
    s.state["progress"].append("旧步骤")
    agent_run("帮我写首诗", s, isolated)

    assert s.state["goal"] == "写一首诗"
    assert s.state["progress"] == []
    assert s.state["status"] == "done"


def test_state_revive_on_continue(isolated, monkeypatch):
    """done 后追问同一任务 -> goal 保留, 状态先复活、回答完再次 done"""
    monkeypatch.setattr(
        config.client.chat.completions, "create",
        fake_llm([make_response(content="补充回答")]),
    )
    s = isolated.create()
    s.state["goal"] = "原任务"
    s.state["status"] = "done"
    agent_run("原任务再解释一下", s, isolated)

    assert s.state["goal"] == "原任务"
    assert s.state["status"] == "done"

def test_summary_generated_on_trim(isolated, monkeypatch):
    """recent 超 token 被裁 -> 旧历史作为 dropped 交摘要器 -> summary 更新"""
    monkeypatch.setattr(config, "RECENT_TOKEN_LIMIT", 1)
    monkeypatch.setattr(config, "KEEP_RECENT_TOKENS", 1)

    captured = {}

    def fake_summarize(old_summary, dropped, archive_path=""):
        captured["dropped"] = dropped
        return "合并后的摘要"

    monkeypatch.setattr("agent.runtime.summarize", fake_summarize)
    monkeypatch.setattr(
        config.client.chat.completions, "create",
        fake_llm([make_response(content="答")]),
    )
    s = isolated.create()
    # 先铺垫一批"此前积累的历史对话", 它们超 token 后应成为 dropped
    s.messages.extend([
        {"role": "user", "content": "第一个问题,内容要足够长一点"},
        {"role": "assistant", "content": "第一个回答,也故意写得比较长"},
        {"role": "user", "content": "第二个问题,同样需要够长才行"},
    ])

    agent_run("你好", s, isolated) # isolated —— 隔离的

    assert s.summary == "合并后的摘要"

    # 裁剪(trim)后本轮 user 位于窗口开头、被保留; 三条历史进 dropped;
    # 主循环随后追加模型的最终回答, 因此窗口末尾是 assistant "答"
    assert s.messages[0]["role"] == "user"
    assert s.messages[0]["content"] == "你好"
    assert s.messages[-1]["role"] == "assistant"
    assert s.messages[-1]["content"] == "答"
    assert len(captured["dropped"]) == 3

def test_read_file_bypasses_cap(isolated, monkeypatch, tmp_path):
    """read_file 是下钻通道: 即使结果超硬上限, 也必须原样进上下文, 不能被二次截断"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "TOOL_RESULT_TOKEN_LIMIT", 10)

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    long_text = "归档细节内容" * 100                 # 600 字, 小于默认 max_chars=800
    (data_dir / "arc.txt").write_text(long_text, encoding="utf-8")

    tc = make_tool_call("c1", "read_file", '{"path": "data/arc.txt"}')
    monkeypatch.setattr(
        config.client.chat.completions, "create",
        fake_llm([
            make_response(tool_calls=[tc]),
            make_response(content="读完了"),
        ]),
    )
    s = isolated.create()
    agent_run("读文件", s, isolated)

    tool_msgs = [m for m in s.messages if m["role"] == "tool"]
    assert tool_msgs[0]["content"] == long_text     # 完整无截断; 若不豁免这里就会挂

def test_dropped_archived_before_summarize(isolated, monkeypatch, tmp_path):
    """测试是否 **\"先归档, 后摘要\"** ? """
    import os, json
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "RECENT_TOKEN_LIMIT", 1)
    monkeypatch.setattr(config, "KEEP_RECENT_TOKENS", 1)
    monkeypatch.setattr(config, "ARCHIVE_DIR", str(tmp_path / "data" / "archive"))

    seen = {}

    def fake_summarize(old_summary, dropped, archive_path=""):
        seen["path"] = archive_path
        return "摘要带指针"

    monkeypatch.setattr("agent.runtime.summarize", fake_summarize)
    monkeypatch.setattr(
        config.client.chat.completions, "create",
        fake_llm([make_response(content="答")]),
    )
    s = isolated.create()
    s.messages.extend([
        {"role": "user", "content": "第一个问题要足够长一点"},
        {"role": "assistant", "content": "第一个回答也写得长一些"},
    ])
    sid = s.id
    agent_run("你好", s, isolated)

    assert s.summary == "摘要带指针"
    assert sid in seen["path"] and seen["path"].endswith(".json")
    with open(seen["path"].replace("/", os.sep), encoding="utf-8") as f:
        payload = json.load(f)
    assert payload["count"] == 2

def test_new_task_clears_recent_but_keeps_summary(isolated, monkeypatch):
    """新任务轮转: recent 清空, summary 跨任务保留(含旧任务归档指针)"""
    monkeypatch.setattr(
        "agent.runtime.classify_turn",
        lambda state, recent, msg: {"relation": "new_task", "new_goal": "全新任务"},
    )
    monkeypatch.setattr(
        config.client.chat.completions, "create",
        fake_llm([make_response(content="好的")]),
    )
    s = isolated.create()
    s.messages.extend([
        {"role": "user", "content": "旧任务对话要足够长一点"},
        {"role": "assistant", "content": "旧任务回答也要写长一些"},
    ])
    s.state["status"] = "done"
    s.summary = "旧任务摘要, 指针 [归档: data/archive/x.json]"

    agent_run("全新的事情", s, isolated)

    assert s.messages[0] == {"role": "user", "content": "全新的事情"}
    assert s.messages[-1]["role"] == "assistant"
    assert len(s.messages) == 2            # 旧对话被清空
    assert s.summary.startswith("旧任务摘要")  # summary 不受轮转影响

