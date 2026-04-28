from bs4 import BeautifulSoup

from wx_content_mesh.services.renderer import WeChatMarkdownRenderer


def _styles(tag) -> str:
    return tag.get("style", "")


def test_renderer_outputs_inline_style():
    html = WeChatMarkdownRenderer("wemd_clean").render("# 标题\n\n> [!TIP] 提示\n> 内容\n\n正文 **重点**")
    assert "style=" in html
    assert "data-callout" in html
    assert "重点" in html


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

    assert "background:#fffdf8" in _styles(root)
    assert "border:1px solid #ddd2c5" in _styles(root)
    assert "var(" not in _styles(root)
    assert "color:#2d2a26" in _styles(paragraph)


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
