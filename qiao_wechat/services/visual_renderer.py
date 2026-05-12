from __future__ import annotations

import base64
import re
import urllib.parse
import zlib

from ..config import get_settings

_PLANTUML_BLOCK_RE = re.compile(r"^```plantuml\r?\n([\s\S]*?)\r?\n```[ \t]*$", re.M)
_GRAPHVIZ_BLOCK_RE = re.compile(r"^```(?:graphviz|dot)\r?\n([\s\S]*?)\r?\n```[ \t]*$", re.M)
_BLOCK_DOLLAR_RE = re.compile(r"^\s*\$\$\s*\r?\n([\s\S]*?)\r?\n\$\$\s*$", re.M)
_BLOCK_LATEX_RE = re.compile(r"\\\[\s*([\s\S]*?)\s*\\\]", re.M)
_INLINE_LATEX_RE = re.compile(r"\\\(([^\\]*(?:\\.[^\\]*)*?)\\\)")
_INLINE_DOLLAR_RE = re.compile(r"(?<!\\)(?<!\$)\$(?!\$)([^\n$]+?)\$(?!\$)")


class WeChatVisualRenderer:
    def __init__(self):
        self.settings = get_settings()

    def transform_markdown(self, markdown_text: str) -> str:
        transformed = _PLANTUML_BLOCK_RE.sub(lambda match: self._render_diagram_block("plantuml", match.group(1)), markdown_text)
        transformed = _GRAPHVIZ_BLOCK_RE.sub(lambda match: self._render_diagram_block("graphviz", match.group(1)), transformed)
        transformed = _BLOCK_DOLLAR_RE.sub(lambda match: self._render_formula_block(match.group(1)), transformed)
        transformed = _BLOCK_LATEX_RE.sub(lambda match: self._render_formula_block(match.group(1)), transformed)
        transformed = _INLINE_LATEX_RE.sub(lambda match: self._render_formula_inline(match.group(1)), transformed)
        transformed = _INLINE_DOLLAR_RE.sub(lambda match: self._render_formula_inline(match.group(1)), transformed)
        return transformed

    def kroki_url(self, diagram_type: str, code: str, *, output_format: str = "svg") -> str:
        encoded = self._encode_kroki(code.strip())
        base = self.settings.kroki_base_url.rstrip("/")
        return f"{base}/{diagram_type}/{output_format}/{encoded}"

    def latex_url(self, expression: str) -> str:
        base = self.settings.latex_render_base_url.rstrip("?")
        encoded = urllib.parse.quote(expression.strip(), safe="")
        return f"{base}?{encoded}"

    def _render_diagram_block(self, diagram_type: str, code: str) -> str:
        src = self.kroki_url(diagram_type, code)
        label_map = {
            "plantuml": "PlantUML",
            "graphviz": "Graphviz",
        }
        label = label_map.get(diagram_type, diagram_type.title())
        return (
            f'<figure data-diagram="{diagram_type}" style="margin:16px 0;text-align:center;">'
            f'<img src="{src}" alt="{label} diagram" '
            'style="max-width:100%;height:auto;display:block;margin:0 auto;"/>'
            "</figure>"
        )

    def _render_formula_block(self, expression: str) -> str:
        src = self.latex_url(expression)
        return (
            '<section data-formula="block" style="margin:16px 0;text-align:center;">'
            f'<img src="{src}" alt="Formula" '
            'style="max-width:100%;height:auto;display:inline-block;vertical-align:middle;"/>'
            "</section>"
        )

    def _render_formula_inline(self, expression: str) -> str:
        src = self.latex_url(expression)
        return (
            '<span data-formula="inline" style="display:inline-flex;align-items:center;vertical-align:middle;">'
            f'<img src="{src}" alt="Formula" '
            'style="height:auto;vertical-align:middle;max-width:100%;"/>'
            "</span>"
        )

    @staticmethod
    def _encode_kroki(code: str) -> str:
        compressed = zlib.compress(code.encode("utf-8"), 9)
        return base64.urlsafe_b64encode(compressed).decode("ascii")
