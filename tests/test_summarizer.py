import config
from unittest.mock import MagicMock
from agent import summarizer

def _reply(text: str):
    """伪造一个类似 OpenAI ChatCompletion 的返回值对象"""
    msg = MagicMock()
    msg.content = text
    r = MagicMock()
    r.choices = [MagicMock(message=msg)]
    return r

def test_summarize_merges_old_and_new(monkeypatch):
    """测试【旧摘要】 + 【新被裁消息】能否正常合并"""
    def fake_create(**kw):
        prompt = kw["messages"][1]["content"]
        assert "旧结论" in prompt          # 旧摘要进去了
        assert "很早的问题" in prompt      # 新被裁消息进去了
        return _reply("合并摘要: 旧结论 + 新事实")
    monkeypatch.setattr(config.client.chat.completions, "create", fake_create)

    out = summarizer.summarize("旧结论", [{"role": "user", "content": "很早的问题"}])
    assert "合并摘要" in out


def test_summarize_no_dropped_returns_old():
    """测试【空列表】生成摘要的功能"""
    assert summarizer.summarize("旧摘要", []) == "旧摘要"


def test_summarize_api_error_keeps_old(monkeypatch):
    """测试: 模型调用失败时, 是否保留【旧摘要】"""
    def boom(**kw):
        raise RuntimeError("挂了")
    monkeypatch.setattr(config.client.chat.completions, "create", boom)
    assert summarizer.summarize("旧摘要", [{"role": "user", "content": "x"}]) == "旧摘要"


def test_summarize_empty_output_keeps_old(monkeypatch):
    """测试: 模型返回【空白内容】时, 是否保留【旧摘要】"""
    monkeypatch.setattr(config.client.chat.completions, "create",
                        lambda **kw: _reply("   "))
    assert summarizer.summarize("旧摘要", [{"role": "user", "content": "x"}]) == "旧摘要"

def test_summarize_receives_archive_pointer(monkeypatch):
    """
    测试:
    1. "归档指针" 是否会被包含在发给模型的 prompt 中
    2. "摘要" 最终是否会保留归档标记
    """
    seen = {}

    def fake_create(**kw):
        seen["prompt"] = kw["messages"][1]["content"]
        return _reply("摘要正文, 细节见 [归档: data/archive/x.json]")

    monkeypatch.setattr(config.client.chat.completions, "create", fake_create)
    out = summarizer.summarize(
        "旧摘要", [{"role": "user", "content": "新消息"}],
        "data/archive/x.json",
    )
    assert "data/archive/x.json" in seen["prompt"]
    assert "[归档" in out
