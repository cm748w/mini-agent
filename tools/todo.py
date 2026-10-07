import os
import json
import tempfile
from datetime import datetime
from filelock import FileLock
from .registry import registry

# 保存 todo 的文件路径
TODO_FILE = "data/todos.json"

# 抢锁超时: 竞争时最多等10秒, 如果超过 10秒 就抛异常
LOCK_TIMEOUT = 10

def _today() -> str:
    """
    **返回**: 今天的月和日
    """
    return datetime.now().strftime("%m月%d日")

def _next_id(todos: list[dict]) -> int:
    """
    **功能**: 基于现有【清单】生成下一个【编号】\n
    **返回**: 下一个【编号】
    """
    max_id = 0
    for t in todos:
        tid = t.get("id")
        # bool 是 int 的子类, 显式排除; 只认 真正的【正整数】
        if isinstance(tid, int) and not isinstance(tid, bool) and tid > max_id:
            max_id = tid
    # 返回【编号】
    return max_id + 1

def _load() -> list[dict]:
    """
    **功能**: 从文件读取【最新清单】\n
    **返回**: 
    """
    if not os.path.exists(TODO_FILE):
        return []
    try:
        with open(TODO_FILE, "r", encoding="utf-8") as f:
            # 把文件内容解析成 Python对象 
            raw = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Todo 文件读取失败, 本次以空清单处理: {e}")
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            # 把坏掉的 todo.json 改名成 todo.json.bad.<ts>
            os.replace(TODO_FILE, f"{TODO_FILE}.bad.{ts}")
        except OSError:
            pass
        return []
    if not isinstance(raw, list):
        print("Todo 文件格式错误(顶层不是 list), 本次以空清单处理")
        return []
    # 静默丢弃非 dict 元素
    return [item for item in raw if isinstance(item, dict)]

def _save(todos: list[dict]) -> None:
    """**功能**: 把【待办清单】安全地写回磁盘"""
    """整份清单原子写: 同目录临时文件 + fsync + os.replace。"""
    dirname = os.path.dirname(TODO_FILE) or "."
    os.makedirs(dirname, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dirname, prefix=".todos.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(todos, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, TODO_FILE)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise

# 添加一条 Todo
@registry.register(
    name="add_todo",
    description="添加一条Todo, 添加成功返回'True', 失败返回'False'",
    parameters={
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "Todo内容"},
        },
        "required": ["task"],
    },
)
def add_todo(task: str) -> bool:
    """
    **功能**: 【添加待办】\n
    **返回**: 
    - True  —— 添加成功
    - False —— 添加失败 (文件不会被写坏)
    
    ---
    事务: 加锁 -> 重读最新 -> 追加 -> 写回 -> 释放
    """
    task = task.strip()
    if not task:
        return False

    lock = FileLock(TODO_FILE + ".lock", timeout=LOCK_TIMEOUT)
    try:
        with lock:
            todos = _load()
            todos.append({"id": _next_id(todos), "date": _today(), "task": task})
            _save(todos)
    except Exception as e:
        print(f"添加 Todo 失败: {type(e).__name__}: {e}")
        return False
    return True

# 删除一条 Todo
@registry.register(
    name="delete_todo",
    description="删除一条Todo, 成功返回True, 失败/Todo不存在返回False",
    parameters={
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "待删除Todo"},
        },
        "required": ["task"],
    },
)
def delete_todo(task: str) -> bool:
    """
    **功能**: 【删除待办】\n
    **返回**: 
    - True  —— 删除成功
    - False —— 删除失败 (文件不会被写坏)
    
    ---
    事务: 加锁 -> 重读最新 -> 找到则删除并写回 -> 释放
    """
    task = task.strip()

    lock = FileLock(TODO_FILE + ".lock", timeout=LOCK_TIMEOUT)
    try:
        with lock:
            todos = _load()
            for i, t in enumerate(todos):
                if t.get("task") == task:
                    todos.pop(i)
                    _save(todos)
                    return True
            return False
    except Exception as e:
        print(f"删除 Todo 失败: {type(e).__name__}: {e}")
        return False

# 查询全部 Todo
@registry.register(
    name="all_todo",
    description="返回全部Todo,每行一条; 没有Todo时返回'还没有任何Todo'",
    parameters={"type": "object", "properties": {}},
)
def all_todo() -> str:
    """
    **返回**: 【所有待办】

    ---
    只读: 原子 replace 保证不会读到半截, 无需加锁。
    """
    todos = _load()
    if not todos:
        return "还没有任何Todo"
    return "\n".join(
        f"#{t.get('id')} {t.get('date')} {t.get('task')}" for t in todos
    )

