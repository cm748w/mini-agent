def needs_compaction(messages: list, threshold: int) -> bool:
    return len(messages) > threshold

def compact(messages: list, keep_recent: int) -> list:
    """滑动窗口: 保留 system 消息和最近 keep_recent 条, 丢弃其余的消息"""
    # 第1步: 找出所有开头的 system 消息, 并将其 "单独保留"
    head = []
    idx = 0
    while idx < len(messages) and messages[idx]["role"] == "system":
        head.append(messages[idx])
        idx +=1

    # 第2步: 计算保留段"起点"
    start = max(idx, len(messages) - keep_recent)

    # 第3步: 保留段不以 "孤儿 tool 消息" 开头
    """tool 消息必须紧跟在带 tool_calls 的 assistant 后面,
    一旦切在 tool 消息处,API 会因配对缺失报错"""
    while start < len(messages) and messages[start]["role"] == "tool":
        start +=1

    return head + messages[start:]
