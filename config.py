import os
import logging
from dotenv import load_dotenv
from openai import OpenAI

# 加载 .env 环境变量
load_dotenv()

# 模型名称
MODEL_NAME = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")

# 最大轮次限制
MAX_ROUNDS = int(os.getenv("MAX_ROUNDS", 8))

# 会话文件
SESSIONS_FILE = os.getenv("SESSIONS_FILE", "data/sessions.json")

# 消息列表的最大 消息条数
MAX_MESSAGES = int(os.getenv("MAX_MESSAGES", 20))
# 裁剪时要保留的 消息条数
KEEP_RECENT = int(os.getenv("KEEP_RECENT", 12))

# 摘要(summary)的最大 token 数
SUMMARY_MAX_TOKENS = int(os.getenv("SUMMARY_MAX_TOKENS", 600))


# ===== 上下文总预算 =====
# deepseek-flash(DeepSeek-V4.1-Flash): 窗口 1M、最大输出 384K、思考模式默认开启。

# 为控成本先保守取 100K 起步, 验证稳定后可上调 200K(等效 64K 窗口的比例约 370K)。
CONTEXT_BUDGET = int(os.getenv("CONTEXT_BUDGET", 100000))

# 输出+思考预留: 思考模式官方 max_tokens 默认 64K(高强度可达 128K), 这里取 65536
RESERVED_OUTPUT_TOKENS = int(os.getenv("RESERVED_OUTPUT_TOKENS", 65536))

# State 安全余量: 1M 窗口下 500 比例过低, 提到 4096
STATE_RESERVE_TOKENS = int(os.getenv("STATE_RESERVE_TOKENS", 4096))

# recent 硬触发线 = 总预算 - 输出 - 摘要 - State。只有逼近这里才摘要(低频)
RECENT_TOKEN_LIMIT = (
    CONTEXT_BUDGET - RESERVED_OUTPUT_TOKENS
    - SUMMARY_MAX_TOKENS - STATE_RESERVE_TOKENS
)
# 裁剪保留线 = 硬线约 55%, 一次裁约 45%、减少摘要次数; 仍允许 env 覆盖
KEEP_RECENT_TOKENS = int(         # round —— 把数字四舍五入到最近的整数
    os.getenv("KEEP_RECENT_TOKENS", round(RECENT_TOKEN_LIMIT * 0.55)) 
)


# artifacts —— agent运行过程中产出的、需要落盘保护的 "产物文件"
# 超长输出落盘目录
ARTIFACTS_DIR = os.getenv("ARTIFACTS_DIR", "data/artifacts")

# 单条工具结果进上下文的硬上限
TOOL_RESULT_TOKEN_LIMIT = int(os.getenv("TOOL_RESULT_TOKEN_LIMIT", 800))

# archive /ˈɑːrkaɪv/ —— 档案; 把 ... 归档 (阿凯屋)
# 被裁原始消息的回档目录
ARCHIVE_DIR = os.getenv("ARCHIVE_DIR", "data/archive")

client = OpenAI(
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    api_key = os.getenv("DEEPSEEK_API_KEY")
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mini_agent")

# 停掉第三方库的INFO日志(仅保留其WARNING/ERROR日志)
# for noisy_logger in ("httpx", "httpcore", "openai"):
#     logging.getLogger(noisy_logger).setLevel(logging.WARNING)

# 配置合法性检查(fail fast)
if RECENT_TOKEN_LIMIT <= 0:
    raise ValueError(
        f"CONTEXT_BUDGET({CONTEXT_BUDGET}) 过小: 扣除输出预留 "
        f"{RESERVED_OUTPUT_TOKENS}、摘要 {SUMMARY_MAX_TOKENS}、State "
        f"{STATE_RESERVE_TOKENS} 后 recent 预算为 {RECENT_TOKEN_LIMIT}, 请调大 CONTEXT_BUDGET"
    )
if RECENT_TOKEN_LIMIT <= KEEP_RECENT_TOKENS:
    raise ValueError(
        f"RECENT_TOKEN_LIMIT({RECENT_TOKEN_LIMIT}) 必须大于 "
        f"KEEP_RECENT_TOKENS({KEEP_RECENT_TOKENS}), 否则触发却无消息可裁"
    )

# trim 裁剪单条消息
# drop 裁剪消息列表