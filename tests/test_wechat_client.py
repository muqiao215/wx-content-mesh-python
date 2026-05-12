from pathlib import Path

import pytest

from qiao_wechat.config import get_plain_env
from qiao_wechat.models import WeChatAccount
from qiao_wechat.services.wechat_client import WeChatApiClient


def test_validate_inline_image_rejects_gif(tmp_path: Path):
    path = tmp_path / "inline.gif"
    path.write_bytes(b"GIF89a")

    with pytest.raises(ValueError, match="inline image"):
        WeChatApiClient._validate_upload_image(
            path,
            allowed={"image/jpeg", "image/png"},
            max_bytes=1024 * 1024,
            label="inline image",
        )


def test_validate_inline_image_rejects_large_file(tmp_path: Path):
    path = tmp_path / "inline.png"
    path.write_bytes(b"0" * (1024 * 1024 + 1))

    with pytest.raises(ValueError, match="too large"):
        WeChatApiClient._validate_upload_image(
            path,
            allowed={"image/jpeg", "image/png"},
            max_bytes=1024 * 1024,
            label="inline image",
        )


def test_secret_can_be_resolved_from_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("WX_ACCOUNT_MAIN_SECRET", raising=False)
    (tmp_path / ".env").write_text("WX_ACCOUNT_MAIN_SECRET=dotenv-secret\n", encoding="utf-8")
    get_plain_env.cache_clear()

    account = WeChatAccount(name="main", appid="wx123", secret_env_name="WX_ACCOUNT_MAIN_SECRET")

    try:
        assert WeChatApiClient(None, account).secret == "dotenv-secret"
    finally:
        get_plain_env.cache_clear()
