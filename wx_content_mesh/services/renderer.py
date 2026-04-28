from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import markdown as md
from bs4 import BeautifulSoup, Tag


@dataclass(frozen=True)
class Theme:
    name: str
    root: str
    styles: dict[str, str]
    callouts: dict[str, str]


THEMES: dict[str, Theme] = {
    "wemd_clean": Theme(
        name="wemd_clean",
        root="max-width:677px;margin:0 auto;padding:28px 18px;color:#2b2b2b;background:#ffffff;"
        "font-size:16px;line-height:1.86;letter-spacing:0.02em;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Helvetica Neue',Arial,sans-serif;",
        styles={
            "h1": "font-size:24px;line-height:1.35;font-weight:800;color:#111;margin:0 0 22px;padding:0 0 12px;border-bottom:2px solid #111;letter-spacing:0.02em;",
            "h2": "font-size:20px;line-height:1.45;font-weight:800;color:#111;margin:34px 0 16px;padding-left:12px;border-left:4px solid #111;",
            "h3": "font-size:18px;line-height:1.5;font-weight:750;color:#222;margin:28px 0 12px;",
            "p": "margin:13px 0;color:#2b2b2b;line-height:1.86;",
            "strong": "font-weight:800;color:#111;",
            "em": "font-style:normal;color:#555;background:linear-gradient(transparent 65%,#fff1a8 0);",
            "blockquote": "margin:22px 0;padding:14px 16px;border-left:4px solid #d8d8d8;background:#fafafa;color:#555;border-radius:8px;",
            "code": "font-family:Menlo,Consolas,monospace;font-size:90%;background:#f4f4f5;color:#d14;padding:2px 5px;border-radius:4px;",
            "pre": "margin:18px 0;padding:14px 16px;background:#1f2937;color:#f9fafb;border-radius:10px;overflow:auto;line-height:1.65;font-size:13px;",
            "a": "color:#576b95;text-decoration:none;border-bottom:1px dotted #576b95;",
            "img": "display:block;max-width:100%;height:auto;margin:18px auto;border-radius:10px;",
            "table": "width:100%;border-collapse:collapse;margin:20px 0;font-size:14px;line-height:1.6;",
            "th": "border:1px solid #e5e7eb;background:#f7f7f7;padding:8px 9px;font-weight:750;color:#111;",
            "td": "border:1px solid #e5e7eb;padding:8px 9px;color:#333;",
            "ul": "margin:12px 0;padding-left:1.2em;color:#333;",
            "ol": "margin:12px 0;padding-left:1.2em;color:#333;",
            "li": "margin:6px 0;line-height:1.75;",
            "hr": "border:none;border-top:1px solid #e5e7eb;margin:28px 0;",
        },
        callouts={
            "note": "border:1px solid #dbeafe;background:#eff6ff;color:#1e3a8a;",
            "tip": "border:1px solid #bbf7d0;background:#f0fdf4;color:#14532d;",
            "important": "border:1px solid #ddd6fe;background:#f5f3ff;color:#4c1d95;",
            "warning": "border:1px solid #fde68a;background:#fffbeb;color:#78350f;",
            "caution": "border:1px solid #fecaca;background:#fef2f2;color:#7f1d1d;",
        },
    ),
    "wemd_card": Theme(
        name="wemd_card",
        root="max-width:677px;margin:0 auto;padding:30px 18px;color:#222;background:#fbfaf7;"
        "font-size:16px;line-height:1.9;letter-spacing:0.03em;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Helvetica Neue',Arial,sans-serif;",
        styles={
            "h1": "font-size:25px;line-height:1.38;font-weight:800;color:#1f2937;margin:0 0 24px;padding:22px 18px;background:#ffffff;border-radius:18px;box-shadow:0 6px 24px rgba(0,0,0,.06);",
            "h2": "font-size:20px;font-weight:800;color:#1f2937;margin:36px 0 18px;padding:10px 14px;background:#ffffff;border-radius:12px;box-shadow:0 3px 14px rgba(0,0,0,.045);",
            "h3": "font-size:18px;font-weight:750;color:#374151;margin:28px 0 12px;",
            "p": "margin:13px 0;color:#2d2d2d;line-height:1.9;",
            "strong": "font-weight:800;color:#0f172a;background:linear-gradient(transparent 62%,#fde68a 0);",
            "em": "font-style:normal;color:#9a3412;",
            "blockquote": "margin:22px 0;padding:16px 18px;background:#ffffff;border-radius:16px;color:#4b5563;box-shadow:0 4px 18px rgba(0,0,0,.05);",
            "code": "font-family:Menlo,Consolas,monospace;font-size:90%;background:#fff7ed;color:#c2410c;padding:2px 5px;border-radius:4px;",
            "pre": "margin:18px 0;padding:14px 16px;background:#0f172a;color:#f8fafc;border-radius:14px;overflow:auto;line-height:1.65;font-size:13px;",
            "a": "color:#2563eb;text-decoration:none;border-bottom:1px dotted #93c5fd;",
            "img": "display:block;max-width:100%;height:auto;margin:18px auto;border-radius:16px;box-shadow:0 5px 18px rgba(0,0,0,.08);",
            "table": "width:100%;border-collapse:separate;border-spacing:0;margin:20px 0;font-size:14px;line-height:1.6;background:#fff;border-radius:12px;overflow:hidden;",
            "th": "border:1px solid #eee;background:#f3f4f6;padding:8px 9px;font-weight:750;color:#111;",
            "td": "border:1px solid #eee;padding:8px 9px;color:#333;",
            "ul": "margin:12px 0;padding-left:1.2em;color:#333;",
            "ol": "margin:12px 0;padding-left:1.2em;color:#333;",
            "li": "margin:6px 0;line-height:1.75;",
            "hr": "border:none;border-top:1px dashed #d6d3d1;margin:30px 0;",
        },
        callouts={
            "note": "border:1px solid #bfdbfe;background:#eff6ff;color:#1e40af;",
            "tip": "border:1px solid #86efac;background:#f0fdf4;color:#166534;",
            "important": "border:1px solid #c4b5fd;background:#f5f3ff;color:#5b21b6;",
            "warning": "border:1px solid #fcd34d;background:#fffbeb;color:#92400e;",
            "caution": "border:1px solid #fca5a5;background:#fef2f2;color:#991b1b;",
        },
    ),
}

_EXTERNAL_LINK_RE = re.compile(r"^https?://", re.I)
_CALLOUT_RE = re.compile(r"^>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*(.*)$", re.I)


class WeChatMarkdownRenderer:
    """WeMD-like renderer implemented in Python.

    Design choices copied as concepts, not code:
    - Markdown first
    - inline styles only
    - local preview artifact
    - external links can be moved to footnotes because WeChat blocks many links
    - callout syntax similar to GitHub Alerts
    """

    def __init__(
        self,
        theme_name: str = "wemd_clean",
        external_links_as_footnotes: bool = True,
        include_toc: bool = False,
    ):
        if theme_name not in THEMES:
            raise ValueError(f"Unknown theme: {theme_name}. Available: {', '.join(THEMES)}")
        self.theme = THEMES[theme_name]
        self.external_links_as_footnotes = external_links_as_footnotes
        self.include_toc = include_toc

    def render(self, markdown_text: str, *, title: str | None = None) -> str:
        prepared = self._preprocess_callouts(markdown_text)
        body = md.markdown(
            prepared,
            extensions=["extra", "tables", "fenced_code", "sane_lists", "nl2br", "md_in_html"],
            output_format="html5",
        )
        soup = BeautifulSoup(body, "html.parser")
        self._ensure_title(soup, title)
        self._inline_styles(soup)
        self._fix_code_blocks(soup)
        headings = self._normalize_headings(soup)
        if self.include_toc and headings:
            self._insert_toc(soup, headings)
        if self.external_links_as_footnotes:
            self._links_to_footnotes(soup)
        root = soup.new_tag("section", id="wemd")
        root["style"] = self.theme.root
        for node in list(soup.contents):
            root.append(node)
        page = BeautifulSoup("", "html.parser")
        page.append(root)
        return str(page)

    def save_preview(self, html_body: str, out_path: Path, *, page_title: str = "Preview") -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        document = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(page_title)}</title>
<style>
body {{ margin:0; padding:32px 0; background:#f3f4f6; }}
.preview-shell {{ max-width:430px; margin:0 auto; background:#fff; min-height:100vh; box-shadow:0 12px 40px rgba(0,0,0,.12); }}
@media (max-width: 520px) {{ body {{ padding:0; }} .preview-shell {{ max-width:none; box-shadow:none; }} }}
</style>
</head>
<body><main class="preview-shell">{html_body}</main></body>
</html>"""
        out_path.write_text(document, encoding="utf-8")
        return out_path

    def replace_image_sources(self, html_body: str, uploader: Callable[[str], str]) -> str:
        soup = BeautifulSoup(html_body, "html.parser")
        for img in soup.find_all("img"):
            src = img.get("src")
            if not src or src.startswith(("data:", "https://mmbiz.qpic.cn/", "http://mmbiz.qpic.cn/")):
                continue
            img["data-original-src"] = src
            img["src"] = uploader(src)
        return str(soup)

    def _preprocess_callouts(self, text: str) -> str:
        lines = text.splitlines()
        out: list[str] = []
        i = 0
        while i < len(lines):
            m = _CALLOUT_RE.match(lines[i])
            if not m:
                out.append(lines[i])
                i += 1
                continue
            kind = m.group(1).lower()
            title = m.group(2).strip() or kind.upper()
            content: list[str] = []
            i += 1
            while i < len(lines) and lines[i].startswith(">"):
                content.append(re.sub(r"^>\s?", "", lines[i]))
                i += 1
            out.append(f'<section data-callout="{kind}" markdown="1"><p data-callout-title="1">{html.escape(title)}</p>')
            out.extend(content)
            out.append("</section>")
        return "\n".join(out)

    def _ensure_title(self, soup: BeautifulSoup, title: str | None) -> None:
        if not title:
            return
        first_heading = soup.find(["h1", "h2"])
        if first_heading and first_heading.get_text(strip=True) == title.strip():
            return
        h1 = soup.new_tag("h1")
        h1.string = title
        soup.insert(0, h1)

    def _inline_styles(self, soup: BeautifulSoup) -> None:
        for tag_name, style in self.theme.styles.items():
            for tag in soup.find_all(tag_name):
                existing = tag.get("style", "")
                tag["style"] = self._merge_style(style, existing)
        for sec in soup.find_all("section"):
            kind = sec.get("data-callout")
            if not kind:
                continue
            callout_style = self.theme.callouts.get(kind, self.theme.callouts["note"])
            sec["style"] = self._merge_style(
                "margin:22px 0;padding:14px 16px;border-radius:12px;line-height:1.75;" + callout_style,
                sec.get("style", ""),
            )
            for title in sec.find_all(attrs={"data-callout-title": "1"}):
                title["style"] = "margin:0 0 8px;font-weight:800;line-height:1.5;"
            sec.attrs.pop("markdown", None)

    def _fix_code_blocks(self, soup: BeautifulSoup) -> None:
        for pre in soup.find_all("pre"):
            code = pre.find("code")
            if code:
                # Inline code style inside pre often creates mixed background in WeChat.
                code["style"] = "font-family:Menlo,Consolas,monospace;background:transparent;color:inherit;padding:0;border-radius:0;white-space:pre;"
        for code in soup.find_all("code"):
            if code.parent and code.parent.name == "pre":
                continue
            code["style"] = self.theme.styles["code"]

    def _normalize_headings(self, soup: BeautifulSoup) -> list[tuple[str, str, str]]:
        headings: list[tuple[str, str, str]] = []
        seen: dict[str, int] = {}
        for tag in soup.find_all(["h1", "h2", "h3"]):
            text = tag.get_text(" ", strip=True)
            if not text:
                continue
            base = self._slugify(text)
            count = seen.get(base, 0)
            seen[base] = count + 1
            slug = base if count == 0 else f"{base}-{count + 1}"
            tag["id"] = slug
            tag["data-heading"] = tag.name
            headings.append((tag.name, text, slug))
        return headings

    def _insert_toc(self, soup: BeautifulSoup, headings: list[tuple[str, str, str]]) -> None:
        toc = soup.new_tag("section")
        toc["data-toc"] = "1"
        toc["style"] = (
            "margin:0 0 26px;padding:14px 16px;border-radius:12px;background:#f8fafc;"
            "color:#475569;font-size:14px;line-height:1.7;"
        )
        title = soup.new_tag("p")
        title["style"] = "margin:0 0 8px;font-weight:800;color:#334155;"
        title.string = "目录"
        toc.append(title)
        for level, text, slug in headings:
            p = soup.new_tag("p")
            indent = "0" if level in ("h1", "h2") else "1em"
            p["style"] = f"margin:4px 0;padding-left:{indent};"
            a = soup.new_tag("a", href=f"#{slug}")
            a["style"] = self.theme.styles["a"]
            a.string = text
            p.append(a)
            toc.append(p)
        first = soup.find(["h1", "h2", "h3", "p", "section", "blockquote", "ul", "ol"])
        if first:
            first.insert_before(toc)
        else:
            soup.append(toc)

    def _links_to_footnotes(self, soup: BeautifulSoup) -> None:
        footnotes: list[tuple[str, str]] = []
        for a in soup.find_all("a"):
            href = a.get("href", "")
            if not _EXTERNAL_LINK_RE.match(href):
                continue
            idx = len(footnotes) + 1
            label = a.get_text(strip=True) or href
            footnotes.append((label, href))
            a["href"] = "#ref-" + str(idx)
            a["style"] = self.theme.styles["a"]
            a.string = f"{label} [{idx}]"
        if not footnotes:
            return
        box = soup.new_tag("section")
        box["style"] = "margin:30px 0 0;padding:14px 16px;border-radius:12px;background:#f8fafc;color:#475569;font-size:13px;line-height:1.7;"
        title = soup.new_tag("p")
        title["style"] = "margin:0 0 8px;font-weight:800;color:#334155;"
        title.string = "参考链接"
        box.append(title)
        for idx, (label, href) in enumerate(footnotes, start=1):
            p = soup.new_tag("p")
            p["style"] = "margin:4px 0;word-break:break-all;"
            p["id"] = f"ref-{idx}"
            p.string = f"[{idx}] {label}: {href}"
            box.append(p)
        soup.append(box)

    @staticmethod
    def _merge_style(base: str, extra: str) -> str:
        if not extra:
            return base
        if not base.endswith(";"):
            base += ";"
        return base + extra

    @staticmethod
    def _slugify(text: str) -> str:
        cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text.lower(), flags=re.U).strip("-")
        return cleaned[:80] or "heading"
