"""配置管理。所有配置从环境变量读取。"""

import os
import logging
from pathlib import Path

from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("coursebook_agent")
logger.setLevel(logging.DEBUG if os.getenv("DEBUG", "false").lower() == "true" else logging.INFO)


class LLMConfig(BaseModel):
    """LLM API 配置。端点和 key 必须由使用者通过环境变量提供。"""

    api_key: str = os.getenv("LLM_API_KEY", "")
    base_url: str = os.getenv("LLM_BASE_URL", "")
    model: str = os.getenv("LLM_MODEL", "")
    timeout: int = int(os.getenv("LLM_TIMEOUT", "120"))


class ServerConfig(BaseModel):
    """服务器配置。"""

    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"


class ZhiyunConfig(BaseModel):
    """In-repository Zhiyun authentication configuration.

    JWT should normally be supplied through ``ZHIYUN_JWT``. A legacy external
    session file can be imported by explicitly setting ``ZHIYUN_SESSION_FILE``;
    no code or executable is loaded from that external location.
    """

    jwt: str = os.getenv("ZHIYUN_JWT", "")
    session_file: Path = Path(
        os.getenv("ZHIYUN_SESSION_FILE", "./data/zhiyun/session.json")
    ).expanduser()

    @property
    def has_credentials(self) -> bool:
        return bool(self.jwt) or self.session_file.exists()


class AppConfig(BaseModel):
    """应用全局配置。"""

    llm: LLMConfig = LLMConfig()
    server: ServerConfig = ServerConfig()
    zhiyun: ZhiyunConfig = ZhiyunConfig()

    data_dir: Path = Path(os.getenv("DATA_DIR", "./data"))
    output_dir: Path = Path(os.getenv("OUTPUT_DIR", "./data/output"))

    def validate(self) -> None:
        """验证必要配置。"""
        if not self.llm.api_key:
            raise ValueError("LLM_API_KEY 未设置，请在 .env 中配置")
        if not self.llm.base_url:
            raise ValueError("LLM_BASE_URL 未设置，请在 .env 中配置（OpenAI 兼容端点，如 https://your-host/v1）")
        if not self.llm.model:
            raise ValueError("LLM_MODEL 未设置，请在 .env 中配置")
        # ZhiyunSource is cache-first: a project can run offline with existing
        # subtitle cache and only needs credentials for a live refresh.

    def ensure_dirs(self) -> None:
        """确保必要目录存在。"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)


config = AppConfig()

try:
    config.validate()
except (ValueError, FileNotFoundError) as e:
    logger.warning(f"配置警告: {e}")

config.ensure_dirs()
