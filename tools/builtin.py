from .registry import registry
from datetime import datetime

@registry.register(
        name="get_current_time",
        description="获取当前日期",
        parameters={
            "type": "object",
            "properties": {},
        },
)
def get_current_time() -> str:
    """获取当前的日期"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
