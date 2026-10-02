from .registry import registry

MOCK_DB = {
    "豆包": "豆包支持对话、写作、编程等任务,是学生党的不二之选",
    "deepseek": "deepseek被誉为AI界的斩杀线,是小康家庭的首选",
    "成都": "成都是四川省省会,以川菜和大熊猫闻名",
}

@registry.register(
    name="search",
    description="""在知识库中搜索关键词,返回相关介绍; 没有相关资料时给出提示。""",
    parameters= {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "要查询的关键词"},
        },
        "required": ["query"]
    }
)
def search(query: str) -> str:
    """在知识库中搜索关键词,返回相关介绍; 没有相关资料时给出提示。"""
    for key, value in MOCK_DB.items():
        if query.lower() in key.lower() or key.lower() in query.lower():
            return value
    return f"没有找到与{query}相关的内容"