from __future__ import annotations

import html
import re
from pathlib import Path


_WIKILINK_IMAGE_RE = re.compile(r"!\[\[([^\]]+)\]\]")
_IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".webp",
    ".svg",
}
_EXPORTED_DIAGRAM_SUFFIXES = {".drawio", ".excalidraw"}


class ObsidianAssetAdapter:
    def rewrite_image_embeds(self, markdown_text: str, *, base_dir: Path | None = None) -> str:
        return _WIKILINK_IMAGE_RE.sub(lambda match: self._replace_embed(match.group(1), base_dir=base_dir), markdown_text)

    def _replace_embed(self, body: str, *, base_dir: Path | None) -> str:
        target, _, option = body.partition("|")
        target = target.strip()
        option = option.strip()
        if not target:
            return f"![[{body}]]"

        resolved = self._resolve_target(target, base_dir=base_dir)
        if resolved is None:
            return f"![[{body}]]"

        alt = Path(target).stem.replace(".excalidraw", "").replace(".drawio", "")
        style = self._style_from_option(option)
        attrs = f' src="{html.escape(resolved)}" alt="{html.escape(alt)}"'
        if style:
            attrs += f' style="{html.escape(style)}"'
        return f"<img{attrs} />"

    def _resolve_target(self, target: str, *, base_dir: Path | None) -> str | None:
        suffixes = Path(target).suffixes
        exported_diagram_suffix = next((suffix for suffix in suffixes if suffix in _EXPORTED_DIAGRAM_SUFFIXES), None)
        if exported_diagram_suffix:
            if base_dir is None:
                return self._fallback_export_name(target, diagram_suffix=exported_diagram_suffix)
            return self._resolve_exported_diagram(target, diagram_suffix=exported_diagram_suffix, base_dir=base_dir)
        if suffixes and suffixes[-1].lower() in _IMAGE_SUFFIXES:
            return target
        return None

    @staticmethod
    def _fallback_export_name(target: str, *, diagram_suffix: str) -> str:
        if target.endswith(diagram_suffix):
            return f"{target}.svg"
        return target

    def _resolve_exported_diagram(self, target: str, *, diagram_suffix: str, base_dir: Path) -> str:
        source = (base_dir / Path(target)).resolve()
        candidates = [
            source.with_suffix(f"{diagram_suffix}.svg"),
            source.with_suffix(f"{diagram_suffix}.png"),
            source.with_suffix(".svg"),
            source.with_suffix(".png"),
            Path(str(source) + ".svg"),
            Path(str(source) + ".png"),
        ]
        for candidate in candidates:
            if candidate.exists():
                try:
                    return str(candidate.relative_to(base_dir))
                except ValueError:
                    return str(candidate)
        return self._fallback_export_name(target, diagram_suffix=diagram_suffix)

    @staticmethod
    def _style_from_option(option: str) -> str | None:
        if not option:
            return None
        if option.isdigit():
            return f"width:{option}px"
        return None
