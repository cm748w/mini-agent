import config
from config import logger
from .prompts import SUMMARIZE_PROMPT

# 摘要器

def _render_messages(messages: list) -> str:
    """**功能:** 把 **消息列表(*messages*)** 渲染成可读文本 **【被裁部分】**\n
    **返回:** 字符串 **(*str*)**
    """
    lines = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            continue
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

def summarize(old_summary: str, dropped: list, archive_path: str = "") -> str:
    """
    **功能:** 通过【旧摘要】【裁剪列表】【归档指针】得到【**新摘要**】\n
    **返回:** 
    - 【新摘要】**(str)** —— 一切顺利的情况
    - 【旧摘要】**(str)** —— 有小插曲的情况
    """

    # 如果【裁剪列表】为空, 则不总结, 并返回【旧摘要】
    if not dropped:
        return old_summary

    # 构建【总结提示词】
    prompt = SUMMARIZE_PROMPT.format(
        old_summary=old_summary or "暂无,这是第一次摘要",
        new_messages=_render_messages(dropped),
        archive_path=archive_path or "(无)",
        max_tokens=config.SUMMARY_MAX_TOKENS,
    )
    try:
        resp = config.client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=[
                {"role": "system", "content": "你是对话摘要器, 只输出摘要正文。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
    except Exception as e:
        logger.warning(f"摘要调用失败, 沿用旧摘要: {type(e).__name__}: {e}")
        # 如果总结失败, 则返回【旧摘要】
        return old_summary

    # 获取并处理模型返回的字符串内容
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        logger.warning("摘要结果为空, 沿用旧摘要")
        # 如果模型的返回内容为空, 则返回【旧摘要】
        return old_summary
    logger.info(f"[摘要已更新]: 约 {len(text)} 字")
    # 返回【新摘要】
    return text

