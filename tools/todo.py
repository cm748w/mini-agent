import os, json
from datetime import datetime
from .registry import registry
import tempfile
TODO_FILE="data/todos.json"
ALL_ID = 0

class Todo:
    date: str     # 例如: "09月29日"
    id: int       # 总编号,从1开始
    task: str     # Todo内容

    def __init__(self, task: str, date: str | None = None, id: int | None = None):
        global ALL_ID

        # 自动编号
        if id is None:
            ALL_ID += 1
            id = ALL_ID

        # 自动取今天
        if date is None:
            date = datetime.now().strftime("%m月%d日")
        
        self.id = id
        self.date = date
        self.task = task

# 添加一条Todo,通过代码实现编号自增和日期生成
@registry.register(
    name="add_todo",
    description="添加一条Todo, 如果添加成功会返回'True', 否则返回'False'",
    parameters={
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "Todo内容"},
        },
        "required": ["task"],
    },
)
def add_todo(task: str) -> bool:
    """添加一条Todo, 如果添加成功会返回'True', 否则返回'False'"""
    task = task.strip()
    if not task:
        return False
    
    global ALL_ID
    old_all_id = ALL_ID

    todo = Todo(task)
    _todos.append(todo)
    
    try:
        _save_todos()
        return True
    except Exception as e:
        _todos.pop()
        ALL_ID = old_all_id
        print(f"保存 Todo 失败: {e}")
        return False

# 删除一条Todo,总编号同时建议
@registry.register(
    name="delete_todo",
    description="删除一条Todo,如果执行成功则返回True,失败则返回False",
    parameters={
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "待删除Todo"},
        },
        "required": ["task"],
    },
)
def delete_todo(task: str) -> bool:
    """删除一条Todo,如果执行成功则返回True,失败/Todo不存在则返回False"""
    for i, todo in enumerate(_todos):
        if todo.task == task:
            removed = _todos.pop(i)
            try:
                _save_todos()
                return True
            except Exception as e:
                _todos.insert(i, removed)
                print(f"保存 Todo 失败: {e}")
                return False
    return False

# 查询所有Todo
@registry.register(
    name="all_todo",
    description="返回全部Todo,每行一条; 没有Todo时返回'还没有任何Todo'",
    parameters={
            "type": "object",
            "properties": {},
    },
)
def all_todo() -> str:
    "返回全部Todo,每行一条; 没有Todo时返回'还没有任何Todo'"
    if not _todos:
        return "还没有任何Todo"
    return "\n".join(f"#{t.id} {t.date} {t.task}" for t in _todos)

def _load_todos() -> list[Todo]:
    if not os.path.exists(TODO_FILE):
        return []
    try:
        with open(TODO_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        # 如果不是list,就返回空列表
        if not isinstance(raw, list):
            print("Todo 文件格式错误")
            return []
    except (json.JSONDecodeError, OSError) as e:
        print(f"Todo 文件读取失败, 以空列表启动: {e}")
        # 备份被损坏的文件
        try:
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")[:-3]
            backup = TODO_FILE + f".bad.{ts}"
            os.replace(TODO_FILE, backup)
            print(f"损坏文件已备份到: {backup}")
        except OSError:
            pass
        return []

    todos = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        tid = item.get("id")
        if isinstance(tid, bool):
            tid = None
        elif isinstance(tid, int) and tid > 0:
            pass
        else:
            try:
                tid = int(tid)
                if tid <= 0:
                    tid = None
            except (TypeError, ValueError):
                tid = None
        task = item.get("task")
        if not isinstance(task, str):
            task = "" if task is None else str(task)
        todos.append(Todo(
            task=task,
            date=item.get("date") or None,
            id = tid,
        ))

    # 把全局编号编进"历史最大 id", 否则新加的待办回合历史编号装车
    global ALL_ID
    ALL_ID = max((t.id for t in todos if t.id is not None), default=0)
    return todos

# 持久化 Todo
def _save_todos() -> None:
    dirname = os.path.dirname(TODO_FILE) or "."
    os.makedirs(dirname, exist_ok=True)

    # 对象转字典
    data = [
        {"date": t.date, "id": t.id, "task": str(t.task)}
        for t in _todos
    ]
    # 在目标目录生成唯一临时文件,保证 os.replace 是同分区原子操作
    fd, tmp = tempfile.mkstemp(dir=dirname, prefix=".todos.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, TODO_FILE)
    except Exception:
        # 写入失败/替换失败时清掉临时文件
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise
# 模块导入时自动恢复 
_todos = _load_todos() # 函数体运行时才找这个变量,定义在后没关系

