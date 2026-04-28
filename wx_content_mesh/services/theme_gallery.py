from __future__ import annotations

import html
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import Article
from .renderer import WeChatMarkdownRenderer
from .theme_manager import ThemeInfo, ThemeManager

_SAMPLE_TITLE = "wx-content-mesh 主题预览"
_SAMPLE_MARKDOWN = """## 紧跟标题的段落

这段专门用来观察 `h2 + p` 的处理方式，顺便看看不同主题的首段节奏。

> [!TIP] 排版检查
> 这里是 callout 提示块，方便对比边框、底色、标题样式。

<div class="card">这是一个 `.card` 容器，里面有一个 <strong>强调重点</strong>。</div>

> 一段普通引用，里面有一个 [外部链接](https://example.com/docs/theme-gallery) 方便看 `blockquote p a`。

### 列表与代码

- 第一项
- 第二项里带 `inline code`
- 第三项带 **重点**

```python
def render_theme(name: str) -> str:
    return f"theme={name}"
```

| 字段 | 说明 |
| --- | --- |
| theme | 当前主题 |
| source | 文章来源 |
| mode | 预览模式 |
"""


@dataclass(frozen=True)
class GallerySource:
    article_id: int | None
    label: str
    title: str
    markdown: str


class ThemeGalleryService:
    def __init__(self, db: Session):
        self.db = db

    def resolve_source(self, article_id: int | None = None) -> tuple[GallerySource, list[Article]]:
        articles = (
            self.db.query(Article)
            .order_by(Article.id.desc())
            .limit(20)
            .all()
        )
        if article_id is not None:
            article = self.db.get(Article, article_id)
            if article:
                return (
                    GallerySource(
                        article_id=article.id,
                        label=f"文章 #{article.id}",
                        title=article.title,
                        markdown=article.markdown,
                    ),
                    articles,
                )
        if articles:
            article = articles[0]
            return (
                GallerySource(
                    article_id=article.id,
                    label=f"文章 #{article.id}",
                    title=article.title,
                    markdown=article.markdown,
                ),
                articles,
            )
        return (GallerySource(article_id=None, label="内置示例", title=_SAMPLE_TITLE, markdown=_SAMPLE_MARKDOWN), articles)

    def build_page(self, article_id: int | None = None) -> str:
        source, articles = self.resolve_source(article_id)
        themes = ThemeManager().list_themes()
        cards = [
            self._build_card(theme, source.title, source.markdown)
            for theme in themes
        ]
        options = ['<option value="">内置示例</option>']
        for article in articles:
            selected = ' selected="selected"' if source.article_id == article.id else ""
            options.append(
                f'<option value="{article.id}"{selected}>#{article.id} {html.escape(article.title[:48])}</option>'
            )

        shortcuts = "".join(
            f'<a class="chip" href="#theme-{theme.name}">{html.escape(theme.metadata.display_name)}</a>'
            for theme in themes
        )
        content = "".join(cards)
        selected_hint = html.escape(source.label)
        selected_title = html.escape(source.title)
        options_html = "".join(options)
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Theme Gallery</title>
<style>
:root {{
  color-scheme: light;
  --bg: #f3f4f6;
  --panel: #ffffff;
  --line: #d6d9df;
  --text: #111827;
  --muted: #6b7280;
  --accent: #2563eb;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif;
}}
.toolbar {{
  position: sticky;
  top: 0;
  z-index: 20;
  background: rgba(243, 244, 246, 0.96);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--line);
}}
.toolbar-inner {{
  max-width: 1480px;
  margin: 0 auto;
  padding: 16px 20px;
}}
.toolbar-top {{
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}}
.title {{
  font-size: 18px;
  font-weight: 700;
}}
.meta {{
  color: var(--muted);
  font-size: 13px;
}}
form {{
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}}
select, button {{
  height: 36px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fff;
  padding: 0 12px;
  font-size: 14px;
}}
button {{
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
  font-weight: 600;
}}
.chips {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}}
.chip {{
  display: inline-flex;
  align-items: center;
  height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: #fff;
  color: var(--text);
  text-decoration: none;
  font-size: 13px;
}}
.gallery {{
  max-width: 1480px;
  margin: 0 auto;
  padding: 24px 20px 40px;
}}
.grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: 18px;
}}
.card {{
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
  overflow: hidden;
  min-width: 0;
}}
.card-head {{
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 14px 16px;
  border-bottom: 1px solid var(--line);
}}
.card-title {{
  font-size: 15px;
  font-weight: 700;
}}
.card-subtitle {{
  color: var(--muted);
  font-size: 12px;
}}
.shell {{
  margin: 0 auto;
  max-width: 430px;
  min-height: 720px;
  background: #fff;
  box-shadow: inset 0 0 0 1px rgba(17, 24, 39, 0.06);
}}
@media (max-width: 800px) {{
  .gallery {{ padding-left: 12px; padding-right: 12px; }}
  .toolbar-inner {{ padding-left: 12px; padding-right: 12px; }}
  .grid {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>
  <header class="toolbar">
    <div class="toolbar-inner">
      <div class="toolbar-top">
        <div>
          <div class="title">Theme Gallery</div>
          <div class="meta">{selected_hint} · {selected_title}</div>
        </div>
        <form method="get" action="/preview/themes">
          <select name="article_id">
            {options_html}
          </select>
          <button type="submit">切换文章</button>
        </form>
      </div>
      <nav class="chips">{shortcuts}</nav>
    </div>
  </header>
  <main class="gallery">
    <section class="grid">{content}</section>
  </main>
</body>
</html>"""

    def _build_card(self, theme: ThemeInfo, title: str, markdown: str) -> str:
        rendered = WeChatMarkdownRenderer(theme_name=theme.name, include_toc=True).render(markdown, title=title)
        display_name = html.escape(theme.metadata.display_name)
        source = html.escape(theme.metadata.source)
        theme_name = html.escape(theme.name)
        return f"""
<article class="card" id="theme-{theme_name}">
  <header class="card-head">
    <div>
      <div class="card-title">{display_name}</div>
      <div class="card-subtitle">{theme_name} · {source} · stylesheet -> inline</div>
    </div>
    <a class="chip" href="#theme-{theme_name}">定位</a>
  </header>
  <div class="shell">{rendered}</div>
</article>"""
