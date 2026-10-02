import tools
from tools import registry
import pytest

def test_registry_contains_required_tools():
    names = [s["function"]["name"] for s in registry.schemas()]
    assert "calculator" in names
    assert "search" in names
    assert "add_todo" in names

def test_schema_shape():
    schema = registry.schemas()[0]
    assert schema["type"] == "function"
    assert "name" in schema["function"]
    assert "parameters" in schema["function"]

def test_unknown_tool_raises():
    with pytest.raises(KeyError):
        registry.execute("不存在的工具")

def test_contains_protocol():
    assert "calculator" in registry
    assert "瞎编的" not in registry