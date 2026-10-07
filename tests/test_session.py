from agent.session import SessionManager

def test_session_isolation(tmp_path):
    """测试 **窗口隔离** """
    mgr = SessionManager()
    s1 = mgr.create("窗口1")
    s2 = mgr.create("窗口2")
    s1.messages.append({"role": "user", "content": "数字7"})
    s2.messages.append({"role": "user", "content": "数字9"})

    path = str(tmp_path / "sessions.json")
    mgr.save_all(path)

    mgr2 = SessionManager()
    mgr2.load_all(path)
    assert "数字7" in mgr2.get(s1.id).messages[0]["content"]
    assert "数字9" in mgr2.get(s2.id).messages[0]["content"]
    assert len(mgr2.list_sessions()) == 2

def test_summary_roundtrip(tmp_path):
    """摘要持久化测试"""
    mgr = SessionManager()
    s = mgr.create()
    s.summary = "早先对话的摘要"
    path = str(tmp_path / "sessions.json")
    mgr.save_all(path)

    mgr2 = SessionManager()
    mgr2.load_all(path)
    assert mgr2.get(s.id).summary == "早先对话的摘要"
