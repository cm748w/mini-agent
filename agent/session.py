import uuid, os, json
from dataclasses import dataclass, field
from datetime import datetime

SESSIONS_FILE = os.getenv("SESSIONS_FILE", "data/sessions.json")

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

@dataclass
class Session:
    id: str
    name: str
    messages: list = field(default_factory=list) # 会话的全部对话历史
    created_at: str = field(default_factory=now_str)
    updated_at: str = field(default_factory=now_str)

    def touch(self):
        self.updated_at = now_str()

class SessionManager:
    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def create(self, name: str | None = None) -> Session:
        # 防止碰撞
        while True:
            session_id = uuid.uuid4().hex[:8]
            if session_id not in self._sessions:
                break
        # 没传的时候name为默认值
        if name is None:
            name = f"会话-{session_id}"
        s = Session(id=session_id, name=name)
        self._sessions[session_id] = s
        return s
    # 通过键来获取Session
    def get(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            raise KeyError(f"session:{session_id}不存在")
        return self._sessions[session_id]
    # 获取Session列表
    def list_sessions(self) -> list[Session]:
        return list(self._sessions.values())
    
    # 返回列表副本的写法【记得import copy】
    # def list_sessions(self) -> list[Session]:
    # return [copy.deepcopy(s) for s in self._sessions.values()]

    def save_all(self, path: str) -> None:
        data = {
            "version": 1,
            "sessions": [
                {
                    "id": s.id,
                    "name": s.name,
                    "created_at": s.created_at,
                    "updated_at": s.updated_at,
                    "messages": s.messages,
                }
                for s in self._sessions.values()
            ],
        }
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def load_all(self, path: str) -> None:
        if not os.path.exists(path): 
            return
        # 读取失败时不让程序崩溃
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"会话文件读取失败,将以空会话启动: {e}")
            return
        self._sessions.clear()
        # 重建Session, 登记进字典
        for item in (data.get("sessions") or []): # 防null
            sid = item.get("id")
            if not sid:
                continue # 跳过损坏条目
            s = Session(
                id=sid,
                name=item.get("name", f"会话-{sid}"),
                messages=item.get("messages", []),
                created_at=item.get("created_at", ""),
                updated_at=item.get("updated_at", ""),
            )
            self._sessions[s.id] = s

manager = SessionManager()
manager.load_all(SESSIONS_FILE)