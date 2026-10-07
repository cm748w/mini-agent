import json
import unicodedata # 查询 Unicode 字符属性、做 Unicode 规范化的工具模块
from .state import state_message

def needs_compaction(messages: list, threshold: int) -> bool:
    """判断\"是否压缩上下文\"\n
    **返回bool值**"""
    return len(messages) > threshold # threshold 临界值 or 阈值

def compact(messages: list, keep_recent: int) -> list:
    """**功能:** 裁剪消息列表\n
    **返回:** 裁剪后的消息列表\n
    ---
    **规则:** 保留的 system 消息和最近 keep_recent 条
    """
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

# strip —— 剥离
def _strip_system(messages: list) -> list:
    """
    **功能**: 去掉【消息列表】中的【系统提示词】\n
    **返回**: 不含 **system** 的【消息列表】
    """
    # 系统提示词 和 State 统一由 build_context 注入
    return [m for m in messages if m.get("role") != "system"]

# estimate —— 估算
def estimate_tokens(text: str) -> int:
    """
    **功能**: 估算【token数】\n
    **返回**: 估算结果 **(int)**
    """
    # 全角字符(中日文、全角标点)约 1 token/字,半角约4字符/token
    wide = sum(1 for ch in text if unicodedata.east_asian_width(ch) in ("W", "F"))
    return wide + (len(text) - wide) // 4

def message_tokens(message: dict) -> int:
    """估算**单条消息**(含tool_calls)的token\n
    +4 作为消息结构开销\n
    返回token数(int)"""
    return estimate_tokens(json.dumps(message, ensure_ascii=False)) + 4

def history_tokens(messages: list) -> int:
    """计算消息列表的token\n
    返回token数(int)"""
    return sum(message_tokens(m) for m in messages)

def over_token_limit(messages: list, token_limit: int) -> bool:
    """
    **功能**: 判断【消息列表】的 **token** 是否超限\n
    **返回**: 【**bool**】
    """
    return history_tokens(messages) > token_limit

# trim —— 裁剪
# tuple —— 不可变序列
def trim_recent_by_tokens(recent: list, keep_tokens: int) -> tuple[list, list]:
    """**功能:** 通过【token数】裁剪消息列表\n
    **返回:** 【消息列表】的 **保留部分** 和 **裁剪部分**
    """
    # 按 token 滑动裁剪: 
    # 从最新消息往前累加,保留累计约keep_tokens的部分
    # 被裁部分 会被 交给 摘要器
    recent = _strip_system(recent)
    
    # 保留段的起始索引, 也等于要裁掉的消息数
    # recent[kept_idx:]：要保留的消息
    # recent[:kept_idx]：要裁掉的消息
    kept_idx = len(recent) # 初始化时, 默认裁掉所有消息(recent列表)

    # 已经决定保留的 token数
    budget = 0 # 刚开始的时候, 默认裁掉所有消息, 所以保留数为 0

    while kept_idx > 0:
        # ntx —— 当前正在检查的那条消息的 token 数
        nxt = message_tokens(recent[kept_idx - 1])

        if budget > 0 and budget + nxt > keep_tokens:
            # 如果存过消息, 且 (已存消息token数+当前消息token数) > 可存token数上线
            # 则停止循环
            break
        budget += nxt # 如果没存过消息, 则享受一次保底
        kept_idx -= 1 # 意味着多存一条 message
    # 保留段不能以孤儿 tool 开头(其 assistant 已被裁): 向新方向跳过开头的 tool
    while kept_idx < len(recent) and recent[kept_idx]["role"] == "tool":
        kept_idx += 1 # 意味着舍弃一条 tool 消息
    return recent[kept_idx:], recent[:kept_idx]

# trim —— 裁剪
def trim_recent_by_count(recent: list, keep_count: int) -> tuple[list, list]:
    """**功能:** 通过【条数】裁剪消息列表\n
    **返回:** 下一轮需要的**消息列表** 和 待总结的**消息列表**
    """
    recent = _strip_system(recent)
    idx = max(0, len(recent) - keep_count) # idx —— 被裁剪消息的数量
    
    # 下一轮消息列表的第一条消息不能是 tool (tool消息必须跟在assistant消息后面)
    while idx < len(recent) and recent[idx]["role"] == "tool":
        idx += 1
    return recent[idx:], recent[:idx]

# summary header —— 摘要标题
SUMMARY_HEADER = "【历史摘要 Summary】以下是更早对话的摘要, 其中的结论与事实仍然有效:"

# context —— 上下文/语境
# *recent —— 把recent(列表)中的元素逐个展开, 作为当前返回列表的 独立元素 插入末尾 [可迭代对象解包]
def build_context(system_prompt: str, state: dict, summary: str, recent: list) -> list:
    """
    **功能**: 构建【上下文】, 形成 **System + State + Summary + Recent History**
    **返回**：【上下文列表】 
    - system_prompt: 基础人设|规则
    - state: 最终目标&进度(JSON) 【始终保留】
    - summary: 历史摘要
    - recent: 最近的对话窗口 【唯一被裁剪的部分】
    """
    # 提纯【消息列表】(去掉 system 提示词)
    recent = _strip_system(recent)

    # block —— 大块
    # 构建【system提示词】列表
    blocks = [{"role": "system", "content": system_prompt}]
    # 把【总结】构建为【system 提示词】
    if summary:
        blocks.append({
            "role": "system",
            "content": f"{SUMMARY_HEADER}\n{summary}",
        })
    # 追加【state】包装的【system提示词】
    blocks.append(state_message(state)) # append —— 加一条
    # 把提纯后的【消息列表】追加到 block
    blocks.extend(recent) # extend —— 加多条

    # 返回构建好的【新消息列表】
    return blocks

# truncate —— 截断
def truncate_by_tokens(text: str, token_limit: int) -> str:
    """**功能**: 按 **token_limit** 截取 **text** \n
    **返回**: 返回 **【截取前缀】** """
    # 粗略截取

    # 返回字符的 token 总数
    total = 0.0

    # 遍历字符串
    for i, ch in enumerate(text): # 把 "字符串" 当成 "字符数组" 遍历, 返回 "索引" 和 "值"
        # 每次 ch 的估计 token 数
        cost = 1.0 if unicodedata.east_asian_width(ch) in ("W", "F") else 0.25

        # 如果加上这个字符(ch), token 会超标, 那么我们就返回这个字符(ch)之前的所有字符
        if total + cost > token_limit:
            return text[:i]
        # 只要不超标, 就往死里加
        total += cost
    # 如果所有字符的 token 之和仍未超标, 那就返回原字符串
    return text

