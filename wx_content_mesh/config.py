from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings.

    Keep secrets in env vars. For multiple WeChat accounts, put each account in the DB
    and store secret_env_name instead of raw secret when possible.
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="WCM_", extra="ignore")

    database_url: str = "sqlite:///./data/wx_content_mesh.db"
    output_dir: Path = Path("./outputs")
    upload_dir: Path = Path("./uploads")
    request_timeout: float = 20.0
    token_margin_seconds: int = 300
    use_stable_token: bool = True
    app_base_url: str = "http://127.0.0.1:8000"
    default_author: str = ""
    render_theme: str = "wemd_clean"
    publish_policy: Literal["draft_only", "preview_then_submit", "submit_direct"] = "draft_only"

    def ensure_dirs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        if self.database_url.startswith("sqlite:///"):
            db_path = Path(self.database_url.replace("sqlite:///", ""))
            db_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
