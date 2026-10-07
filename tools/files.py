import os
from .registry import registry

_ALLOWED_ROOTS = ("data", "logs") # 根目录下可读的文件夹
_DEFAULT_MAX_CHARS = 800 # 需要更多时, 模型自己调大 max_chars

# normalized —— 规范化后的
# absolute path —— 绝对路径
def _is_allowed(norm_abs_path: str) -> bool:
    """
    **功能**: 判断【绝对路径】是否在白名单上
    **返回**: 布尔值

    ---
    调用前, 必须真正规范化过路径!!!
    """

    # 遍历 "白名单"
    for root in _ALLOWED_ROOTS:
        # 把 root 转 "绝对路径"
        root_abs = os.path.abspath(root)

        """
        separator —— 路径分隔符
        # os.sep —— 代表操作系统的路径分隔符 "\\"(Windows)  "/"(Linux|Mac)
        # .startwith() —— 表示"以某个前缀开头", 返回 bool 【不判断文件是否存在】！！！
        """

        # 如果 "目标路径" 正好等于根目录, True
        # 如果 "目标路径" 以 `根目录 + 路径分隔符` 开头, 说明它在根目录下面, True
        if norm_abs_path == root_abs or norm_abs_path.startswith(root_abs + os.sep):
            return True
    # 默认不允许
    return False

@registry.register(
    name="read_file",
    description="读取已落盘的文本文件(如: 工具的完整输出、历史归档), 返回文件内容",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径(仅支持 `data/` `logs/`下)"},
            "max_chars": {"type": "integer", "description": "最多返回的字符数, 默认 800, 如有必要, 可自行扩大"},
        },
        "required": ["path"],
    }
)

# 需要更多时, 模型自己调大【max_chars】
def read_file(path: str, max_chars: int = _DEFAULT_MAX_CHARS) -> str:

    """
    os.path.normpath() 规范【路径字符串】, 统一路径分隔符
    os.path.abspath()  转成绝对路径, 并规范化
    os.path.realpath() 解析符号链接, 得到真实路径
    """
    norm = os.path.abspath(os.path.normpath(path))
    # 判断 norm 是否属于白名单
    if not _is_allowed(norm):
        return (
            f"无权读取 {path} "
            f"只能读取 {','.join(_ALLOWED_ROOTS)} 目录下的文件"
        )
    # 判断 norm 是否是文件
    if not os.path.isfile(norm):
        return f"文件不存在: {path}"
    try:
        with open(norm, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars + 1)
    except OSError as e:
        return f"文件读取失败: {type(e).__name__}: {e}"

    if len(content) > max_chars:
        return (
            content[:max_chars] +
            f"\n[文件超过 {max_chars} 字符, 已裁断。\n可调大 max_chars 继续读]"
        )
    return content












