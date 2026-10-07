import pytest
import tools
from tools import registry
import tools.todo as todo_mod
import threading

# calculator
def test_calculator_add():
    assert registry.execute("calculator", a=1, b=2, operator="+") == "3"

def test_calculator_div_zero():
    result = registry.execute("calculator", a=1, b=0, operator="/")
    assert "除数" in result

def test_calculator_bad_operator():
    result = registry.execute("calculator", a=1, b=2, operator="%")
    assert "不支持" in result

# search
def test_search_hit():
    assert "川菜" in registry.execute("search", query="成都")

def test_search_miss():
    assert "没有找到" in registry.execute("search", query="火星房价")

def test_read_file_roundtrip(monkeypatch, tmp_path):
    """测试 读文件 功能"""
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "a.txt").write_text("完整内容123", encoding="utf-8")
    assert registry.execute("read_file", path="data/a.txt") == "完整内容123"

def test_read_file_rejects_outside(monkeypatch, tmp_path):
    """测试 是否拒读 白名单之外的路径"""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.txt").write_text("secret", encoding="utf-8")
    assert "无权" in registry.execute("read_file", path=str(tmp_path / "x.txt"))
    assert "无权" in registry.execute("read_file", path="../x.txt")

def test_read_file_missing(monkeypatch, tmp_path):
    """测试 文件不存在 时的错误处理"""
    monkeypatch.chdir(tmp_path)
    assert "不存在" in registry.execute("read_file", path="data/nope.txt")

@pytest.fixture
def todo_file(monkeypatch, tmp_path):
    """把 todo 数据文件(及锁文件)指到临时目录"""
    # 测试隔离，保证每个测试从干净环境开始
    path = str(tmp_path / "todos.json")
    monkeypatch.setattr(todo_mod, "TODO_FILE", path)
    return path

def test_todo_flow(todo_file):
    # 验证 todo 的基本流程
    assert registry.execute("add_todo", task="交周报") is True
    listed = registry.execute("all_todo")
    assert "交周报" in listed
    assert registry.execute("delete_todo", task="交周报") is True
    assert registry.execute("delete_todo", task="交周报") is False

def test_add_todo_blank(todo_file):
    # 验证 add_todo 是否拒绝【空字符串】或【纯空白字符串】
    assert registry.execute("add_todo", task="   ") is False

def test_todo_id_increments(todo_file):
    # 验证【新任务】会分配【递增ID】
    # 验证 all_todo 展示时带有【编号】
    registry.execute("add_todo", task="事项A")
    registry.execute("add_todo", task="事项B")
    listed = registry.execute("all_todo")
    assert "#1" in listed and "#2" in listed

def test_concurrent_add_no_lost_update(todo_file):
    # 验证【并发添加】时不会丢失更新

    # 并发数量
    n = 20

    def worker(i):
        registry.execute("add_todo", task=f"并发事项{i}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    todos = todo_mod._load()
    assert len(todos) == n                  # 一条不丢
    ids = [t["id"] for t in todos]
    assert len(set(ids)) == n               # 编号唯一、无覆盖

