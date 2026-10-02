import pytest
import tools
from tools import registry

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


# todo: 注意全局 _todos 会跨测试累积,先清空再测
from tools.todo import _todos, _save_todos

def test_todo_flow():
    _todos.clear()
    assert registry.execute("add_todo", task="交周报") is not None
    listed = registry.execute("all_todo")
    assert "交周报" in listed
    assert registry.execute("delete_todo", task="交周报") is True
    assert registry.execute("delete_todo", task="交周报") is False
    _todos.clear()
