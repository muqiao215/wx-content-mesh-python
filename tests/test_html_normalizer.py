from wx_content_mesh.services.html_normalizer import HtmlNormalizer


def test_normalize_moves_img_dimensions_to_style_and_restores_src():
    html = """
    <section>
      <!-- comment -->
      <script>window.bad = true</script>
      <img data-src="demo.png" width="320" height="180" style="display: block; " />
    </section>
    """

    normalized = HtmlNormalizer().normalize(html)

    assert "<!--" not in normalized
    assert "<script" not in normalized
    assert 'src="demo.png"' in normalized
    assert 'width="320"' not in normalized
    assert 'height="180"' not in normalized
    assert 'style="display:block;width:320px;height:180px"' in normalized


def test_compact_removes_editor_noise_but_keeps_style_and_img_dimensions():
    html = """
    <section id="root" class="editor-shell" data-node-id="1">
      <p class="body" data-track="x" style=" color: #222 ; ">正文</p>
      <img class="photo" data-origin-src="demo.png" data-src="demo.png" width="200" />
    </section>
    """

    compacted = HtmlNormalizer().compact(html)

    assert 'id="root"' not in compacted
    assert 'class="editor-shell"' not in compacted
    assert 'data-node-id=' not in compacted
    assert 'data-track=' not in compacted
    assert 'style="color:#222"' in compacted
    assert 'src="demo.png"' in compacted
    assert 'style="width:200px"' in compacted
