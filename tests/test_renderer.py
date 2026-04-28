from wx_content_mesh.services.renderer import WeChatMarkdownRenderer


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
