from __future__ import annotations

import hashlib
import mimetypes
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

    def _download(self, url: str) -> Path:
        parsed = urlparse(url)
        suffix = Path(parsed.path).suffix or ".jpg"
        name = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24] + suffix
        target = self.settings.upload_dir / name
        if target.exists() and target.stat().st_size > 0:
            return target
        resp = requests.get(url, timeout=self.settings.request_timeout, headers={"User-Agent": "wx-content-mesh/0.2"})
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
