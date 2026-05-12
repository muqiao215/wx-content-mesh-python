from __future__ import annotations

import re

from bs4 import BeautifulSoup, Comment


_IMG_SRC_CANDIDATES = ("src", "data-src", "data-original-src", "data-url")


class HtmlNormalizer:
    def normalize(self, content: str) -> str:
        soup = BeautifulSoup(content, "html.parser")

        for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
            comment.extract()

        for tag in soup.find_all(["script", "noscript"]):
            tag.decompose()

        for img in soup.find_all("img"):
            self._ensure_img_src(img)
            self._img_dimensions_to_style(img)

        for tag in soup.find_all(True):
            style = tag.attrs.get("style")
            if style is None:
                continue
            if isinstance(style, list):
                style = " ".join(str(part) for part in style)
            normalized = self._normalize_style(str(style))
            if normalized:
                tag.attrs["style"] = normalized
            else:
                del tag.attrs["style"]

        root = soup.body if soup.body else soup
        html = "".join(str(node) for node in root.contents)
        html = re.sub(r">\s+<", "><", html)
        return html.strip()

    def compact(self, content: str) -> str:
        soup = BeautifulSoup(content, "html.parser")

        for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
            comment.extract()

        for tag in soup.find_all(True):
            if tag.name == "img":
                self._ensure_img_src(tag)
                self._img_dimensions_to_style(tag)

            for attr in list(tag.attrs):
                if attr == "style":
                    continue
                if attr in {"class", "id"} or attr.startswith("data-"):
                    del tag.attrs[attr]

            style = tag.attrs.get("style")
            if style is None:
                continue
            if isinstance(style, list):
                style = " ".join(str(part) for part in style)
            normalized = self._normalize_style(str(style))
            if normalized:
                tag.attrs["style"] = normalized
            else:
                del tag.attrs["style"]

        compacted = str(soup)
        compacted = re.sub(r">\s+<", "><", compacted)
        compacted = re.sub(r"\n+", "", compacted)
        compacted = re.sub(r"\s{2,}", " ", compacted)
        return compacted.strip()

    @staticmethod
    def _ensure_img_src(img) -> None:
        src = img.get("src")
        if src:
            return
        for candidate in _IMG_SRC_CANDIDATES[1:]:
            value = img.get(candidate)
            if value:
                img["src"] = value
                return

    def _img_dimensions_to_style(self, img) -> None:
        style = img.get("style")
        if isinstance(style, list):
            style = " ".join(str(part) for part in style)
        style_map = self._parse_style_map(str(style or ""))

        width = img.get("width")
        height = img.get("height")
        if width and "width" not in style_map:
            style_map["width"] = self._normalize_dimension(str(width))
        if height and "height" not in style_map:
            style_map["height"] = self._normalize_dimension(str(height))
        if width is not None:
            del img.attrs["width"]
        if height is not None:
            del img.attrs["height"]

        if style_map:
            img["style"] = self._normalize_style(";".join(f"{key}:{value}" for key, value in style_map.items()))

    @staticmethod
    def _normalize_dimension(value: str) -> str:
        normalized = value.strip()
        if re.fullmatch(r"\d+", normalized):
            return f"{normalized}px"
        return normalized

    @staticmethod
    def _parse_style_map(style: str) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for declaration in style.split(";"):
            if ":" not in declaration:
                continue
            name, value = declaration.split(":", 1)
            key = name.strip().lower()
            if not key:
                continue
            normalized_value = value.strip()
            if normalized_value:
                mapping[key] = normalized_value
        return mapping

    @staticmethod
    def _normalize_style(style: str) -> str:
        style = re.sub(r"\s*;\s*", ";", style.strip())
        style = re.sub(r"\s*:\s*", ":", style)
        style = re.sub(r";+$", "", style)
        return style
