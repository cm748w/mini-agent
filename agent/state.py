import json
import copy

"""
 State的JSON结构 —— 记录 "目标" 和 "进度" (独立于滑动窗口) (始终保留)
 template —— 模版
 state —— 状态
"""
STATE_TEMPLATE = {
    "goal": "",                 # 最终目标
    "status": "in_progress",    # in_progress | done | blocked ( 进行时 | 完成 | 阻塞 )
    "progress": [],             # 已完成的步骤
    "key_facts": [],            # 需要长期记忆的 "关键事实"
    "next_step": "",            # 下一步的计划
}
_VALID_STATUS = ("in_progress", "done", "blocked")

def new_state() -> dict:
    """返回一份全新的 state (深拷贝,避免多个会话共享同一个 list/dict)"""
    return copy.deepcopy(STATE_TEMPLATE)

# render —— 渲染   indent —— 缩进
# json.dumps() —— 把 python 对象序列化成 JSON 格式的字符串
def render_state(state: dict) -> str:
    """把 state 序列化成可读 JSON 文本"""
    return json.dumps(state, ensure_ascii=False, indent=2)

def state_message(state: dict) -> dict:
    """
    **功能**: 把【state】包装成一条【system 提示词】\n
    **返回**: 包装后的【system 提示词】
    """
    content = (
        "【任务状态 State】: 下面的 JSON 是跨上下文、长期保留的任务目标与进度。"
        "请始终在此基础上继续推进: 不要重复已经完成的步骤, 并与该状态保持一致。\n"
        f"```json\n{render_state(state)}\n```" # 这是 markdown 中 "代码块" 的写法
    )
    return {"role": "system", "content": content}

# normalize —— 标准化
def normalize_state(state: dict) -> dict:
    """以模板为基准, **校正state**(补缺失key、非法类型/枚举重置)\n
    用于旧存档迁移和脏数据兜底"""
    if not isinstance(state, dict):
        return new_state()
    norm = new_state()
    if isinstance(state.get("goal"), str):
        norm["goal"] = state["goal"]
    if state.get("status") in _VALID_STATUS:
        norm["status"] = state["status"]
    for key in ("progress", "key_facts"):
        val = state.get(key)
        if isinstance(val, list) and all(isinstance(x, str) for x in val):
            norm[key] = val
    if isinstance(state.get("next_step"), str):
        norm["next_step"] = state["next_step"]
    return norm

def new_task_state(goal: str) -> dict:
    """
    **功能**: 返回一个新的【state】, 并初始化它的【goal】
    """
    s = new_state()
    s["goal"] = goal
    return s
