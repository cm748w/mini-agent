import os, json
from datetime import datetime
import config
from config import logger
from .memory import estimate_tokens, truncate_by_tokens

# prefix —— 前缀
# suffix —— 后缀
def save_artifact(content: str, prefix: str = "tool", suffix: str = ".txt") -> str:
    """**功能**: 保存 **content**\n
    **返回**: 文件路径"""

    # 读取并规范【路径字符串】
    directory = os.path.normpath(config.ARTIFACTS_DIR)
    # 创建【多级目录】
    os.makedirs(directory, exist_ok=True) # exist_ok —— 如果目录已存在, 不报错
    # 生成【时间戳】
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")[:-3]
    
    # 拼接【完整路径】 (os.path.join —— 跨平台路径拼接, 比手动拼接更安全)
    abs_path = os.path.join(directory, f"{prefix}_{ts}{suffix}")

    # 写入模式打开文件  ("w", 如果文件不存在就创建; 如果已存在就截断覆盖)
    with open(abs_path, "w", encoding="utf-8") as f:
        # 写入文件
        f.write(content)

    # 返回统一的正斜杠路径: 日志/上下文整洁,且跨平台一致
    return abs_path.replace(os.sep, "/") # os.sep —— 操作系统的分隔符

# cap —— 限制
def cap_tool_result(content: str, tool_name: str, token_limit: int) -> str:
    """
    **功能**: 判断 **tool_result** 的大小是否超出限制\n
    **返回**:
    - 【原内容】—— **tool_result** 未超限
    - 【预览 **&** 路径指针】—— **tool_result** 超限"""
    
    # 如果 token 数没超, 那就原样返回
    if estimate_tokens(content) <= token_limit:
        return content

    # 清洗工具名: 只保留字母、数字、下划线 _、连字符 - , 如果清洗后为空，就用 "tool" 兜底
    safe_name = "".join(c for c in tool_name if c.isalnum() or c in "_-") or "tool"
    
    # 保存内容
    path = save_artifact(content, prefix=f"tool_{safe_name}")
    # 返回预览
    preview = truncate_by_tokens(content, token_limit)

    # 打日志
    logger.info(f"工具 {tool_name} 输出超 {token_limit} token, 完整结果已落盘: {path}")

    # 返回【预览】+【指针】
    return (
        f"{preview}\n\n"
        f"[结果过长已截断] 完整内容约 {estimate_tokens(content)} tok, 已保存至: {path}\n"
        f"如需剩余细节, 请调用 read_file 读取该路径。"
    )

# archive /ˈɑːrkaɪv/ —— 把 ... 归档 —— 阿凯屋
# normalize —— 规范化
# 归档消息
def archive_messages(session_id: str, messages: list) -> str:
    """
    **功能**: 归档【被裁剪的消息】到 **`archive/<session_id>/`** 下 \n
    **返回**: 归档文件的路径 **(str)**
    """

    # 拼接【会话文件夹】路径 —— 此时 "路径分隔符" 已被统一
    directory = os.path.normpath(os.path.join(config.ARCHIVE_DIR, session_id)) # session_id 给【不同会话】分目录

    # 创建 directory
    os.makedirs(directory, exist_ok=True)

    # 获取【时间戳】
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]

    # 拼出完整【文件路径】
    file_path = os.path.join(directory, f"dropped_{ts}.json")

    # 构建文件内容
    payload = {
        "session_id": session_id,
        "archived_at": ts,
        "count": len(messages),
        "messages": messages,
    }

    with open(file_path, "w", encoding="utf-8") as f:

        """
        default=str:
          当 JSON 编码器遇到它不知道怎么序列化成 JSON 的对象时,
        就调用 str(obj)，把这个对象转成字符串，然后再写进 JSON。
        ---
        ensure_ascii=False: 不把 "非ASCII" 字符转义
        """

        # 把 python对象 序列化成 JSON格式, 并直接写入文件对象
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    # 正斜杠更加通用
    return file_path.replace(os.sep, "/")