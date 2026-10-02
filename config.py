import os
import logging
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL_NAME = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
MAX_ROUNDS = int(os.getenv("MAX_ROUNDS", 8)) # 最大的轮次限制
SESSIONS_FILE = os.getenv("SESSIONS_FILE", "data/sessions.json")
MAX_MESSAGES = int(os.getenv("MAX_MESSAGES", 20)) # 超过多少条触发压缩
KEEP_RECENT = int(os.getenv("KEEP_RECENT", 12)) # 压缩后保留最近多少条

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

# 停掉第三方库的多余INFO日志(仅保留其WARNING/ERROR日志)
# for noisy_logger in ("httpx", "httpcore", "openai"):
#     logging.getLogger(noisy_logger).setLevel(logging.WARNING)
