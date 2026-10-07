import json
from dataclasses import dataclass, field
from datetime import datetime
import os
from typing import Literal

"""
tool_call_error - 模型给出的参数解析失败
tool_error - 工具执行失败 or 工具不存在
error - API调用失败
fatal - 出现了意料之外的异常
"""
TraceKind = Literal[
    "user", "thought", "assistant_content",
    "tool_call", "tool_call_error", "tool_result",
    "tool_error", "final", "error", "max_rounds", "fatal",
]

@dataclass
class TraceEvent:
    round_idx: int
    kind: TraceKind
    data: dict
    time: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    )

"""
追踪类: 
    用于记录一次【Agent任务】或【请求】从开始到结束的完整执行过程, 
  并把这些步骤串联成一条可查看、可协调、可分析的追踪记录。
"""
class Trace:
    def __init__(self):
        self.events: list[TraceEvent] = []

    def add(self, round_idx: int, kind: TraceKind, **data) -> None:
        self.events.append(TraceEvent(round_idx, kind, data))

    def to_list(self) -> list[dict]:
        return [
            {
                "time": e.time, "round": e.round_idx, 
                "kind": e.kind, "data": e.data
            } for e in self.events
        ]

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        # 原子写入
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_list(), f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
