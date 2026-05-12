from __future__ import annotations

import hashlib
import mimetypes
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import MediaAsset


@dataclass(frozen=True)
class ImageBlob:
    source: str
    path: Path
    sha256: str
    mime_type: str
    width: int | None = None
    height: int | None = None


class ImageService:
    WECHAT_IMAGE_RULES = {
        "inline": {
            "allowed_mime_types": {"image/jpeg", "image/png"},
            "max_bytes": 1 * 1024 * 1024,
            "target_format": "PNG",
            "target_suffix": ".png",
        },
        "cover": {
            "allowed_mime_types": {"image/bmp", "image/png", "image/jpeg", "image/gif"},
            "max_bytes": 10 * 1024 * 1024,
            "target_format": "PNG",
            "target_suffix": ".png",
        },
    }

    def __init__(self, session: Session):
        self.session = session
        self.settings = get_settings()
        self.settings.upload_dir.mkdir(parents=True, exist_ok=True)

    def materialize(self, source: str) -> ImageBlob:
        """Return a local image path for a file path or http(s) URL."""
        if source.startswith(("http://", "https://")):
            path = self._download(source)
        else:
            path = Path(source).expanduser().resolve()
            if not path.exists():
                raise FileNotFoundError(f"image not found: {source}")
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if not mime.startswith("image/"):
            raise ValueError(f"not an image file: {source}")
        width, height = self._size(path)
        return ImageBlob(source=source, path=path, sha256=sha, mime_type=mime, width=width, height=height)

    def find_or_create_asset(self, *, account_id: int | None, source: str, purpose: str, blob: ImageBlob | None = None) -> MediaAsset:
        blob = blob or self.materialize(source)
        asset = (
            self.session.query(MediaAsset)
            .filter(MediaAsset.account_id == account_id, MediaAsset.sha256 == blob.sha256, MediaAsset.purpose == purpose)
            .one_or_none()
        )
        if asset:
            return asset
        asset = MediaAsset(
            account_id=account_id,
            purpose=purpose,
            source=source,
            sha256=blob.sha256,
            mime_type=blob.mime_type,
            width=blob.width,
            height=blob.height,
        )
        self.session.add(asset)
        self.session.flush()
        return asset

    def materialize_asset(self, *, account_id: int | None, source: str, purpose: str) -> tuple[MediaAsset, ImageBlob]:
        """Materialize once and return the matching DB asset.

        Publishing code often needs both the local file path and the database row.
        Keeping this as one operation prevents duplicate downloads for remote images.
        """
        blob = self.materialize(source)
        return self.find_or_create_asset(account_id=account_id, source=source, purpose=purpose, blob=blob), blob

    def prepare_asset_for_wechat(self, *, account_id: int | None, source: str, purpose: str) -> tuple[MediaAsset, ImageBlob]:
        """Return a WeChat-safe image asset for inline/cover upload.

        This normalizes unsupported formats such as SVG into a WeChat-accepted
        raster format and shrinks oversized images before upload.
        """
        if purpose not in self.WECHAT_IMAGE_RULES:
            raise ValueError(f"unsupported wechat image purpose: {purpose}")

        blob = self.materialize(source)
        rules = self.WECHAT_IMAGE_RULES[purpose]
        path = blob.path

        if blob.mime_type not in rules["allowed_mime_types"] or path.stat().st_size > rules["max_bytes"]:
            path = self._normalize_for_wechat(blob, purpose=purpose)
            blob = self.materialize(str(path))

        if blob.mime_type not in rules["allowed_mime_types"]:
            raise ValueError(f"wechat {purpose} image format still unsupported after normalization: {blob.mime_type}")
        if path.stat().st_size > rules["max_bytes"]:
            raise ValueError(f"wechat {purpose} image still exceeds size limit after normalization: {path.stat().st_size}")

        return self.find_or_create_asset(account_id=account_id, source=source, purpose=purpose, blob=blob), blob

    def _download(self, url: str) -> Path:
        parsed = urlparse(url)
        suffix = Path(parsed.path).suffix or ".jpg"
        name = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24] + suffix
        target = self.settings.upload_dir / name
        if target.exists() and target.stat().st_size > 0:
            return target
        resp = requests.get(url, timeout=self.settings.request_timeout, headers={"User-Agent": "qiao-wechat/0.2"})
        resp.raise_for_status()
        if len(resp.content) > 20 * 1024 * 1024:
            raise ValueError("image too large; refusing to store files over 20MB")
        target.write_bytes(resp.content)
        return target

    @staticmethod
    def _size(path: Path) -> tuple[int | None, int | None]:
        try:
            with Image.open(path) as img:
                return img.width, img.height
        except Exception:
            return None, None

    def _normalize_for_wechat(self, blob: ImageBlob, *, purpose: str) -> Path:
        rules = self.WECHAT_IMAGE_RULES[purpose]
        prepared_dir = self.settings.upload_dir / "wechat-prepared"
        prepared_dir.mkdir(parents=True, exist_ok=True)
        target = prepared_dir / f"{blob.sha256[:24]}-{purpose}{rules['target_suffix']}"

        if target.exists() and target.stat().st_size > 0:
            return target

        if blob.mime_type == "image/svg+xml" or blob.path.suffix.lower() == ".svg":
            self._rasterize_svg(blob.path, target)
        else:
            self._rewrite_raster_image(blob.path, target, max_bytes=rules["max_bytes"])

        return target

    @staticmethod
    def _rasterize_svg(source: Path, target: Path) -> None:
        command = ["convert", str(source), str(target)]
        try:
            completed = subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise RuntimeError("ImageMagick 'convert' is required to publish SVG images to WeChat") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise RuntimeError(f"failed to rasterize SVG for WeChat: {stderr or exc}") from exc
        if completed.returncode != 0 or not target.exists():
            raise RuntimeError("failed to rasterize SVG for WeChat")

    @staticmethod
    def _rewrite_raster_image(source: Path, target: Path, *, max_bytes: int) -> None:
        with Image.open(source) as img:
            image = img.convert("RGBA") if img.mode in ("RGBA", "LA", "P") else img.convert("RGB")

            for scale in (1.0, 0.85, 0.7, 0.55, 0.4):
                candidate = image.copy()
                if scale < 1.0:
                    width = max(1, int(candidate.width * scale))
                    height = max(1, int(candidate.height * scale))
                    candidate = candidate.resize((width, height))
                save_kwargs = {"optimize": True}
                if candidate.mode == "RGBA":
                    save_kwargs["compress_level"] = 9
                candidate.save(target, format="PNG", **save_kwargs)
                if target.stat().st_size <= max_bytes:
                    return

        if target.exists() and target.stat().st_size > 0:
            return
        raise RuntimeError(f"failed to normalize image for WeChat: {source}")
