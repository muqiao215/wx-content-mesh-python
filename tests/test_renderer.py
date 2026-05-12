from bs4 import BeautifulSoup

from qiao_wechat.services.obsidian_assets import ObsidianAssetAdapter
from qiao_wechat.services.renderer import WeChatMarkdownRenderer


def _styles(tag) -> str:
    return tag.get("style", "")


def test_renderer_outputs_inline_style():
    html = WeChatMarkdownRenderer("wemd_clean").render("# 标题\n\n> [!TIP] 提示\n> 内容\n\n正文 **重点**")
    assert "style=" in html
    assert "data-callout" in html
    assert "重点" in html


def test_renderer_strips_frontmatter_and_supports_summary_callout():
    markdown = """---
title: "示例标题"
tags:
  - 示例
created: 2026-05-12
---

> [!summary] 一句话总结
> 第一行
> 第二行
"""
    html = WeChatMarkdownRenderer("wechat_baseline").render(markdown, title="示例标题")

    assert "title:" not in html
    assert "created:" not in html
    assert "[!summary]" not in html
    assert 'data-callout="summary"' in html
    assert "一句话总结" in html


def test_renderer_uses_localized_default_summary_callout_title():
    html = WeChatMarkdownRenderer("wechat_baseline").render("> [!summary]\n> 第一行")

    assert 'data-callout="summary"' in html
    assert "摘要" in html


def test_renderer_uses_title_when_markdown_has_no_h1():
    html = WeChatMarkdownRenderer("wemd_clean").render("正文", title="外部标题")
    assert "<h1" in html
    assert "外部标题" in html


def test_renderer_toc_and_external_link_footnote():
    html = WeChatMarkdownRenderer("wemd_clean", include_toc=True).render("## 小节\n\n参考 [链接](https://example.com)")
    assert "data-toc" in html
    assert "参考链接" in html
    assert "https://example.com" in html


def test_replace_image_sources_skips_existing_wechat_cdn():
    renderer = WeChatMarkdownRenderer("wemd_clean")
    html = renderer.replace_image_sources(
        '<section><img src="https://mmbiz.qpic.cn/a.jpg"><img src="./a.png"></section>',
        lambda src: "https://mmbiz.qpic.cn/uploaded.png",
    )
    assert "https://mmbiz.qpic.cn/a.jpg" in html
    assert "https://mmbiz.qpic.cn/uploaded.png" in html


def test_renderer_compiles_adjacent_descendant_and_class_selectors():
    markdown = """
## 小节

紧跟段落

<blockquote><p><a href="https://example.com">引用链接</a></p></blockquote>

<div class="card">卡片 <strong>重点</strong></div>
"""
    html = WeChatMarkdownRenderer("wemd_clean").render(markdown)
    soup = BeautifulSoup(html, "html.parser")

    paragraph = soup.find("h2").find_next_sibling("p")
    assert "margin-top:4px" in _styles(paragraph)

    quote_link = soup.find("blockquote").find("a")
    assert "border-bottom:1px dotted #576b95" in _styles(quote_link)
    assert "color:#576b95" in _styles(quote_link)

    card_strong = soup.select_one(".card strong")
    assert "color:#576b95" in _styles(card_strong)


def test_renderer_resolves_css_variables_and_root_id_theme():
    html = WeChatMarkdownRenderer("default").render("正文")
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find(id="wemd")
    paragraph = root.find("p")

    assert "background:transparent" in _styles(root)
    assert "font-family:\"Noto Serif SC\", \"Source Han Serif SC\", \"Songti SC\", serif" in _styles(root)
    assert "line-height:1.86" in _styles(root)
    assert "color:#2d2a26" in _styles(root)
    assert "border:1px solid #ddd2c5" not in _styles(root)
    assert "var(" not in _styles(root)
    assert "color:#2d2a26" not in _styles(paragraph)


def test_refactored_themes_share_body_first_root_without_card_shell():
    for theme_name in WeChatMarkdownRenderer.available_themes():
        html = WeChatMarkdownRenderer(theme_name).render("# 标题\n\n正文")
        soup = BeautifulSoup(html, "html.parser")
        root = soup.find(id="wemd")
        styles = root.get("style", "")

        assert "font-size:" in styles
        assert "background:transparent" in styles or "background-color:transparent" in styles
        assert "max-width" not in styles
        assert "margin:0 auto" not in styles
        assert "box-shadow" not in styles
        assert "padding:" not in styles
        assert "border-radius" not in styles


def test_renderer_lists_builtin_themes():
    themes = WeChatMarkdownRenderer.available_themes()
    assert {
        "academic_paper",
        "bauhaus",
        "default",
        "grace",
        "knowledge_base",
        "modern",
        "morandi_forest",
        "receipt",
        "simple",
        "wechat_baseline",
        "wechat_standard_v2",
        "wemd_card",
        "wemd_clean",
    }.issubset(set(themes))


def test_renderer_wraps_heading_content_for_wemd_templates():
    html = WeChatMarkdownRenderer("knowledge_base").render("## 小节标题")
    soup = BeautifulSoup(html, "html.parser")
    heading = soup.find("h2")
    content = heading.find("span", class_="content")

    assert content is not None
    assert content.get_text(strip=True) == "小节标题"
    assert "background-color:#F7F6F3" in _styles(content)


def test_renderer_renders_plantuml_graphviz_and_formula_blocks_to_images():
    markdown = r"""
```plantuml
Alice -> Bob: Hello
```

```graphviz
digraph G {
  A -> B;
}
```

$$
E = mc^2
$$

行内公式 \(\alpha + \beta\) 和 $x^2 + y^2$。
"""
    html = WeChatMarkdownRenderer("wemd_clean").render(markdown)
    soup = BeautifulSoup(html, "html.parser")

    plantuml = soup.find("figure", attrs={"data-diagram": "plantuml"})
    graphviz = soup.find("figure", attrs={"data-diagram": "graphviz"})
    block_formula = soup.find("section", attrs={"data-formula": "block"})
    inline_formula = soup.find("span", attrs={"data-formula": "inline"})

    assert plantuml is not None
    assert graphviz is not None
    assert block_formula is not None
    assert inline_formula is not None
    assert "https://kroki.io/plantuml/svg/" in plantuml.find("img")["src"]
    assert "https://kroki.io/graphviz/svg/" in graphviz.find("img")["src"]
    assert "https://latex.codecogs.com/svg.latex?" in block_formula.find("img")["src"]
    assert "https://latex.codecogs.com/svg.latex?" in inline_formula.find("img")["src"]


def test_renderer_rewrites_obsidian_wikilink_image_embeds():
    markdown = (
        "封面：![[imgs/cover.png]]\n\n"
        "手绘：![[diagram.excalidraw|320]]\n\n"
        "流程：![[flow.drawio|480]]"
    )
    html = WeChatMarkdownRenderer("wemd_clean").render(markdown)
    soup = BeautifulSoup(html, "html.parser")
    images = soup.find_all("img")

    assert len(images) == 3
    assert images[0]["src"] == "imgs/cover.png"
    assert images[1]["src"] == "diagram.excalidraw.svg"
    assert "width:320px" in images[1].get("style", "")
    assert images[2]["src"] == "flow.drawio.svg"
    assert "width:480px" in images[2].get("style", "")


def test_wechat_baseline_theme_avoids_card_shell_styles():
    html = WeChatMarkdownRenderer("wechat_baseline").render("# 标题\n\n正文")
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find(id="wemd")

    styles = root.get("style", "")
    assert "font-size:16px" in styles
    assert "line-height:1.82" in styles
    assert "background:transparent" in styles
    assert "box-shadow" not in styles
    assert "max-width" not in styles
    assert "padding:20px" not in styles


def test_obsidian_asset_adapter_prefers_same_directory_drawio_exports(tmp_path):
    article_dir = tmp_path / "post"
    article_dir.mkdir()
    (article_dir / "diagram.drawio.svg").write_text("<svg />", encoding="utf-8")
    (article_dir / "diagram.drawio.png").write_bytes(b"png")
    (article_dir / "diagram.svg").write_text("<svg />", encoding="utf-8")

    html = ObsidianAssetAdapter().rewrite_image_embeds("![[diagram.drawio|320]]", base_dir=article_dir)

    assert 'src="diagram.drawio.svg"' in html
    assert 'style="width:320px"' in html


def test_obsidian_asset_adapter_uses_drawio_png_when_svg_export_is_missing(tmp_path):
    article_dir = tmp_path / "post"
    article_dir.mkdir()
    (article_dir / "diagram.drawio.png").write_bytes(b"png")
    (article_dir / "diagram.svg").write_text("<svg />", encoding="utf-8")

    html = ObsidianAssetAdapter().rewrite_image_embeds("![[diagram.drawio]]", base_dir=article_dir)

    assert 'src="diagram.drawio.png"' in html
