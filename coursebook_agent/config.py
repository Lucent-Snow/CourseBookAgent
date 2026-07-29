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
    """LLM API 配置。"""

    api_key: str = os.getenv("LLM_API_KEY", "")
    base_url: str = os.getenv("LLM_BASE_URL", "http://143.198.25.239:8090/v1")
    model: str = os.getenv("LLM_MODEL", "deepseek-v4-flash")
    timeout: int = int(os.getenv("LLM_TIMEOUT", "120"))


class ServerConfig(BaseModel):
    """服务器配置。"""

    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"


class ZhiyunConfig(BaseModel):
    """zju-scholar 脚本路径配置。"""

    skill_dir: Path = Path(os.getenv("ZJU_SKILL_DIR", "~/.cielagent/skills/zju-scholar")).expanduser()
    python_bin: str = os.getenv("PYTHON_BIN", "python3")

    @property
    def zhiyun_script(self) -> Path:
        return self.skill_dir / "scripts" / "zju_zhiyun.py"

    @property
    def login_script(self) -> Path:
        return self.skill_dir / "scripts" / "zju_login.py"


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
        if not self.zhiyun.zhiyun_script.exists():
            raise FileNotFoundError(
                f"zju-scholar 脚本不存在: {self.zhiyun.zhiyun_script}\n"
                f"请设置 ZJU_SKILL_DIR 指向 zju-scholar 安装目录"
            )

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
