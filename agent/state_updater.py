import re
import json
import config
from config import logger
from .state import render_state
from .prompts import STATE_UPDATE_PROMPT, TURN_CLASSIFY_PROMPT

# 允许模型更新的字段
_LIST_KEYS = ("progress", "key_facts")
_STR_KEYS = ("goal", "next_step")

def _render_events(events: list) -> str:
    """把新消息(本轮)渲染成简洁文本
    \n(只给更新调用看, 不进\"主上下文\")"""
    if not events:
        return "(无新事件)"
    lines = []
    for m in events:
        role = m.get("role")
        if role == "assistant":
            if m.get("tool_calls"):
                calls = [
                    f"{tc['function']['name']}({tc['function']['arguments']})"
                    for tc in m["tool_calls"]
                ]
                lines.append(f"assistant 调用工具: {'; '.join(calls)}")
            if m.get("content"):
                lines.append(f"assistant: {m['content']}")
        elif role == "tool":
            lines.append(f"工具[{m.get('name')}]结果: {m.get('content')}")
        else:
            lines.append(f"{role}: {m.get('content')}")
    return "\n".join(lines)

# extract —— 提取
def _extract_json(text: str) -> dict | None:
    """
    **功能**: 从 **文本** 中提取 **JSON** 数据, 并解析成【Python对象】\n
    **返回**: 【Python对象】
    """
    
    # json.loads() 也可能解析出 list、str、int 等，
    # 所以实际返回类型不一定严格是 dict
    
    text = text.strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except (json.JSONDecodeError, TypeError):
            pass
    left, right = text.find("{"), text.rfind("}")
    if left != -1 and right > left:
        try:
            return json.loads(text[left:right + 1])
        except (json.JSONDecodeError, TypeError):
            pass
    return None

# parse —— 解析
def _merge_state(old: dict, parsed: dict) -> dict:
    """
    **功能**: 通过【模型输出】(parsed), 拼出【新state】\n
    **返回**: 【新state】

    ---
    如果校验失败, 返回【旧state】
    """

    merged = dict(old)
    for key in _LIST_KEYS:
        val = parsed.get(key)
        if isinstance(val, list) and all(isinstance(x, str) for x in val):
            merged[key] = val
    for key in _STR_KEYS:
        val = parsed.get(key)
        if isinstance(val, str):
            merged[key] = val
    return merged

def update_state(old_state: dict, events: list) -> dict:
    """
    **功能**: 根据本轮【消息列表】, 让 LLM 更新 state\n
    **返回**: 新的 state
    
    ---
    失败时(API异常|JSON非法|字段类型错误)原样返回旧state。"""
    prompt = STATE_UPDATE_PROMPT.format(
        old_state=render_state(old_state),
        new_events=_render_events(events),
    )
    try:
        resp = config.client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=[
                {"role": "system", "content": "你是状态更新器, 只输出合法 JSON。"},
                {"role": "user", "content": prompt},
            ],
            # 我用的 Deepseek 官方API, 加上这条↓, 会让 JOSN 输出会更稳
            response_format={"type": "json_object"},
            temperature=0,
        )
    except Exception as e:
        logger.warning(f"State 更新调用失败, 沿用旧 state: {type(e).__name__}: {e}")
        return old_state

    raw = resp.choices[0].message.content or ""
    parsed = _extract_json(raw)
    if parsed is None:
        logger.warning(f"State 更新结果解析失败, 沿用旧 state。raw={raw[:200]}")
        return old_state

    merged = _merge_state(old_state, parsed)
    logger.debug(f"[State 更新]\n{render_state(merged)}")
    return merged

# brief —— 总结
def _recent_brief(recent: list, limit: int = 6) -> str:
    """取最近`{limit}`条消息中的 **非system消息** 作为判定上下文"""
    out = []
    for m in recent[-limit:]:
        if m.get("role") == "system":
            continue
        out.append(f"{m.get('role')}: {str(m.get('content'))[:200]}")
    return "\n".join(out) or "(无)"


def classify_turn(state: dict, recent: list, user_msg: str) -> dict:
    """
    **功能**: 判断 **用户消息** 与【当前任务】的关系\n
    **返回**: **relation** 和 **new_task**

    ---
    "relation": "continue" 或 "new_task"
    """

    # relation —— 新用户消息与当前任务的关系
    # 任何失败都默认 relation 为 continue 
    
    prompt = TURN_CLASSIFY_PROMPT.format(
        state=render_state(state),
        recent=_recent_brief(recent),
        user_msg=user_msg,
    )
    try:
        resp = config.client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=[
                {"role": "system", "content": "你是任务边界判定器, 只输出合法 JSON。"},
                {"role": "user", "content": prompt},
            ],
            # 我用的 Deepseek 官方 API, 加上这条↓, 输出JOSN会更稳
            response_format={"type": "json_object"},
            
            temperature=0, # 确保输出稳定
        )

        # raw —— 原始的
        raw = resp.choices[0].message.content or ""
    except Exception as e:
        logger.warning(f"任务判定调用失败, 默认 continue: {type(e).__name__}: {e}")
        return {"relation": "continue", "new_goal": ""}

    # parse —— 解析
    parsed = _extract_json(raw)
    if not isinstance(parsed, dict) or parsed.get("relation") not in ("continue", "new_task"):
        logger.warning(f"任务判定结果非法, 默认 continue。raw={raw[:200]}")
        return {"relation": "continue", "new_goal": ""}

    new_goal = parsed.get("new_goal")
    if not isinstance(new_goal, str):
        new_goal = ""
    logger.info(f"[任务判定] relation={parsed['relation']} new_goal={new_goal}")
    return {"relation": parsed["relation"], "new_goal": new_goal}

