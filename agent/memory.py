# 判断是否需要进行 "上下文压缩"
def needs_compaction(messages: list, threshold: int) -> bool:
    return len(messages) > threshold # threshold 临界值 or 阈值

# 通过 "活动窗口" 进行 "上下文压缩"
def compact(messages: list, keep_recent: int) -> list:
    """滑动窗口: 保留的 system 消息和最近 keep_recent 条, 丢弃其余的消息"""
    # 第1步: 找出所有开头的 system 消息, 并将其 "单独保留"
    head = [] # 用来存 system 消息
    idx = 0
    # while结束后, idx 等于 system 消息的条数
    while idx < len(messages) and messages[idx]["role"] == "system":
        head.append(messages[idx])
        idx +=1

    # 第2步: 计算保留段"起点"
    start = max(idx, len(messages) - keep_recent)
    # 如果 "系统提示词数量" 超过了 "要舍弃消息的数量"
    # 那么, 我们就把 "系统提示词数量" 作为切割起点

    # 第3步: 跳过 tool 开头的 message
    """ tool消息必须紧跟在带 tool_calls的 assistant后面,
    一旦切在 tool消息处, API会因配对缺失报错"""
    while start < len(messages) and messages[start]["role"] == "tool":
        start +=1

    # 返回切割后的消息列表
    return head + messages[start:]
