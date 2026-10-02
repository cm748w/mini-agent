from dataclasses import dataclass
from typing import Any, Callable

@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema
    func: Callable

    def to_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

class ToolRegistry:
    def __init__(self): # 创建对象是自动调用
        self._tools: dict[str, Tool] = {} # self是正在被创建的对象自己

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def register(self, name: str, description: str, parameters: dict):
        """装饰器工厂: 把被装饰的函数登记进 _tools"""
        def decorator(func: Callable) -> Callable:
            self._tools[name] = Tool(name, description, parameters, func)
            return func
        return decorator

    def get(self, name: str) -> Tool:
        # 主动处理工具不存在的情况
        if name not in self._tools:
            raise KeyError(f"工具不存在:{name}")
        return self._tools[name]

    def schemas(self) -> list[dict]:
        return [tool.to_schema() for tool in self._tools.values()]

    def execute(self, name: str, **kwargs) -> Any:
        return self.get(name).func(**kwargs)

# 全局唯一注册中心
registry = ToolRegistry()