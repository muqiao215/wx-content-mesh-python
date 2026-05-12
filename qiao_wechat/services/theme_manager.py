from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tinycss2
from cssselect2 import compile_selector_list

from .renderer import refresh_theme_cache

THEME_DIR = Path(__file__).resolve().parent.parent / "themes"
METADATA_PATH = THEME_DIR / "metadata.json"
_THEME_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


@dataclass(frozen=True)
class ThemeMeta:
    name: str
    display_name: str
    description: str = ""
    source: str = "local"
    source_url: str | None = None
    preview_cover: str | None = None
    tags: list[str] | None = None
    built_in: bool = False
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class ThemeInfo:
    name: str
    css_path: str
    css_size: int
    metadata: ThemeMeta


class ThemeManager:
    def __init__(self, theme_dir: Path = THEME_DIR, metadata_path: Path = METADATA_PATH):
        self.theme_dir = theme_dir
        self.metadata_path = metadata_path
        self.theme_dir.mkdir(parents=True, exist_ok=True)

    def list_themes(self) -> list[ThemeInfo]:
        metadata = self._load_metadata()
        themes: list[ThemeInfo] = []
        for path in sorted(self.theme_dir.glob("*.css")):
            name = path.stem
            path = self._css_path(name)
            themes.append(
                ThemeInfo(
                    name=name,
                    css_path=str(path),
                    css_size=path.stat().st_size,
                    metadata=self._meta_for(name, metadata.get(name)),
                )
            )
        return themes

    def get_css(self, name: str) -> Path:
        self._validate_name(name)
        path = self._css_path(name)
        if not path.exists():
            raise KeyError(f"theme not found: {name}")
        return path

    def import_css(
        self,
        *,
        name: str,
        css: str,
        display_name: str | None = None,
        description: str = "",
        source: str = "user",
        source_url: str | None = None,
        preview_cover: str | None = None,
        tags: list[str] | None = None,
        overwrite: bool = False,
    ) -> ThemeInfo:
        self._validate_name(name)
        self._validate_css(css)
        path = self._css_path(name)
        if path.exists() and not overwrite:
            raise FileExistsError(f"theme already exists: {name}")

        path.write_text(css, encoding="utf-8")
        now = _now()
        metadata = self._load_metadata()
        previous = metadata.get(name, {})
        metadata[name] = {
            "display_name": display_name or previous.get("display_name") or self._humanize(name),
            "description": description or previous.get("description", ""),
            "source": source or previous.get("source", "user"),
            "source_url": source_url if source_url is not None else previous.get("source_url"),
            "preview_cover": preview_cover if preview_cover is not None else previous.get("preview_cover"),
            "tags": tags if tags is not None else previous.get("tags", []),
            "built_in": bool(previous.get("built_in", False)),
            "created_at": previous.get("created_at") or now,
            "updated_at": now,
        }
        self._write_metadata(metadata)
        refresh_theme_cache()
        return self._theme_info(name)

    def update_metadata(
        self,
        name: str,
        *,
        display_name: str | None = None,
        description: str | None = None,
        source: str | None = None,
        source_url: str | None = None,
        preview_cover: str | None = None,
        tags: list[str] | None = None,
    ) -> ThemeInfo:
        self._validate_name(name)
        if not self._css_path(name).exists():
            raise KeyError(f"theme not found: {name}")
        metadata = self._load_metadata()
        previous = metadata.get(name, {})
        metadata[name] = {
            "display_name": display_name if display_name is not None else previous.get("display_name") or self._humanize(name),
            "description": description if description is not None else previous.get("description", ""),
            "source": source if source is not None else previous.get("source", "local"),
            "source_url": source_url if source_url is not None else previous.get("source_url"),
            "preview_cover": preview_cover if preview_cover is not None else previous.get("preview_cover"),
            "tags": tags if tags is not None else previous.get("tags", []),
            "built_in": bool(previous.get("built_in", False)),
            "created_at": previous.get("created_at"),
            "updated_at": _now(),
        }
        self._write_metadata(metadata)
        return self._theme_info(name)

    def _theme_info(self, name: str) -> ThemeInfo:
        path = self._css_path(name)
        metadata = self._load_metadata()
        return ThemeInfo(name=name, css_path=str(path), css_size=path.stat().st_size, metadata=self._meta_for(name, metadata.get(name)))

    def _css_path(self, name: str) -> Path:
        return self.theme_dir / f"{name}.css"

    def _load_metadata(self) -> dict[str, dict[str, Any]]:
        if not self.metadata_path.exists():
            return {}
        return json.loads(self.metadata_path.read_text(encoding="utf-8"))

    def _write_metadata(self, metadata: dict[str, dict[str, Any]]) -> None:
        payload = json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True)
        self.metadata_path.write_text(payload + "\n", encoding="utf-8")

    def _meta_for(self, name: str, raw: dict[str, Any] | None) -> ThemeMeta:
        raw = raw or {}
        return ThemeMeta(
            name=name,
            display_name=raw.get("display_name") or self._humanize(name),
            description=raw.get("description", ""),
            source=raw.get("source", "local"),
            source_url=raw.get("source_url"),
            preview_cover=raw.get("preview_cover"),
            tags=raw.get("tags") or [],
            built_in=bool(raw.get("built_in", False)),
            created_at=raw.get("created_at"),
            updated_at=raw.get("updated_at"),
        )

    @staticmethod
    def _validate_name(name: str) -> None:
        if not _THEME_NAME_RE.match(name):
            raise ValueError("theme name must match ^[a-z][a-z0-9_]{1,63}$")

    @staticmethod
    def _validate_css(css: str) -> None:
        if len(css.encode("utf-8")) > 512_000:
            raise ValueError("theme CSS is too large; max 512KB")
        stylesheet = tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True)
        compileable_rules = 0
        for node in stylesheet:
            if node.type != "qualified-rule":
                continue
            selector_text = tinycss2.serialize(node.prelude).strip()
            if not selector_text:
                continue
            try:
                selectors = compile_selector_list(selector_text)
            except Exception:
                continue
            declarations = tinycss2.parse_declaration_list(node.content, skip_comments=True, skip_whitespace=True)
            if selectors and any(item.type == "declaration" for item in declarations):
                compileable_rules += 1
        if compileable_rules == 0:
            raise ValueError("theme CSS has no compileable selector/declaration rules")

    @staticmethod
    def _humanize(name: str) -> str:
        return " ".join(part.capitalize() for part in name.split("_"))


def theme_info_to_dict(info: ThemeInfo) -> dict[str, Any]:
    return {
        "name": info.name,
        "css_path": info.css_path,
        "css_size": info.css_size,
        "metadata": asdict(info.metadata),
    }


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
