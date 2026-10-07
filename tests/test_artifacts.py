import os, json, config
from agent import cap_tool_result, estimate_tokens, archive_messages

def test_cap_short_result_untouched(monkeypatch, tmp_path):
    """测试工具结果不落盘的情况"""
    monkeypatch.setattr(config, "ARTIFACTS_DIR", str(tmp_path / "art"))
    assert cap_tool_result("短结果", "search", 500) == "短结果"
    assert not (tmp_path / "art").exists()       # 未超限不落盘

def test_cap_long_result_persists_and_points(monkeypatch, tmp_path):
    """测试工具结果落盘的情况"""
    art_dir = tmp_path / "artifacts"
    monkeypatch.setattr(config, "ARTIFACTS_DIR", str(art_dir))

    long_text = "这是一段很长的工具输出内容。" * 100
    out = cap_tool_result(long_text, "search", 100)

    assert "已保存至" in out and "read_file" in out
    assert estimate_tokens(out) < 100 + 200      # 预览 + 指针说明
    files = list(art_dir.glob("*.txt"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == long_text   # 完整内容无损

def test_archive_messages(monkeypatch, tmp_path):
    """测试 归档消息功能"""
    monkeypatch.setattr(config, "ARCHIVE_DIR", str(tmp_path / "archive"))
    dropped = [{"role": "user", "content": "老消息"}]
    path = archive_messages("abcd1234", dropped)

    assert "abcd1234" in path and path.endswith(".json")
    with open(path.replace("/", os.sep), encoding="utf-8") as f:
        payload = json.load(f)

    assert payload["session_id"] == "abcd1234"
    assert payload["count"] == 1
    assert payload["messages"] == dropped

