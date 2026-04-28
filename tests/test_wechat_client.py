from pathlib import Path

import pytest

from wx_content_mesh.services.wechat_client import WeChatApiClient


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
