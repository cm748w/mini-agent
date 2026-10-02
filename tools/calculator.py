from .registry import registry

@registry.register(
    name="calculator",
    description="用来计算两个数字的加减乘除四则运算",
    parameters= {
        "type": "object",
        "properties": {
            "a": {"type": "number", "description": "第一个数字"},
            "b": {"type": "number", "description": "第二个数字"},
            "operator": {
                "type": "string",
                "enum": ["+", "-", "*", "/"],
                "description": "运算符号"
            },
        },
        "required": ["a", "b", "operator"],
    }
)
def calculator(a: float, b: float, operator: str) -> str:
    """根据operator分发到 + - * / ; 除以0时返回错误而不是崩溃"""
    if operator == "+":
        return str(a+b)
    if operator == "-":
        return str(a-b)
    if operator == "*":
        return str(a*b)
    if operator == "/":
        if b == 0:
            return "错误: 除数不能为 0"
        return str(a/b)
    return f"不支持的运算符: {operator}"
