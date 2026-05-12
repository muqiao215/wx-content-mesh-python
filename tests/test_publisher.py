from pathlib import Path

from bs4 import BeautifulSoup

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from wx_content_mesh.db import Base
from wx_content_mesh.models import Article, ArticleStatus, WeChatAccount
from wx_content_mesh.services.publisher import PublishService
from wx_content_mesh.services.quality_gate import QualityGate
from wx_content_mesh.services.wechat_repo_flow import WechatRepoFlowService
from wx_content_mesh.config import Settings


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


class FakeWeChatClient:
    def __init__(self, session, account):
        self.session = session
        self.account = account

    def get_publish_status(self, publish_id: str):
        return {
            "publish_status": 0,
            "article_id": "wx_article_1",
            "article_detail": {"item": [{"idx": 1, "article_url": "https://mp.weixin.qq.com/s/demo"}]},
        }

    def get_published_article(self, article_id: str):
        return {"news_item": [{"url": "https://mp.weixin.qq.com/s/temp"}]}


def test_poll_publish_status_hydrates_article_url(monkeypatch):
    import wx_content_mesh.services.publisher as publisher_module

    monkeypatch.setattr(publisher_module, "WeChatApiClient", FakeWeChatClient)
    db = _session()
    account = WeChatAccount(name="main", appid="wx_test", raw_secret="secret")
    db.add(account)
    db.flush()
    article = Article(
        account_id=account.id,
        title="标题",
        markdown="正文",
        wx_publish_id="publish_1",
        status=ArticleStatus.publish_submitted,
    )
    db.add(article)
    db.flush()

    payload = PublishService(db).poll_publish_status(article.id)

    assert payload["publish_status"] == 0
    assert article.status == ArticleStatus.published
    assert article.wx_article_id == "wx_article_1"
    assert article.wx_article_url == "https://mp.weixin.qq.com/s/demo"


def test_preview_is_blocked_by_default():
    db = _session()
    account = WeChatAccount(name="main", appid="wx_test", raw_secret="secret")
    db.add(account)
    db.flush()
    article = Article(
        account_id=account.id,
        title="标题",
        markdown="正文",
        wx_draft_media_id="draft_1",
        status=ArticleStatus.draft_created,
    )
    db.add(article)
    db.flush()

    try:
        PublishService(db).send_preview(article.id, towxname="demo-user")
    except ValueError as exc:
        assert "WCM_ALLOW_WECHAT_PREVIEW=true" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("preview should be blocked by default")


def test_publish_is_blocked_by_default():
    db = _session()
    account = WeChatAccount(name="main", appid="wx_test", raw_secret="secret")
    db.add(account)
    db.flush()
    article = Article(
        account_id=account.id,
        title="标题",
        markdown="正文",
        wx_draft_media_id="draft_1",
        status=ArticleStatus.draft_created,
    )
    db.add(article)
    db.flush()

    try:
        PublishService(db).submit_freepublish(article.id)
    except ValueError as exc:
        assert "WCM_ALLOW_WECHAT_PUBLISH=true" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("publish should be blocked by default")


def test_create_wechat_draft_normalizes_svg_cover_and_inline_images(monkeypatch, tmp_path: Path):
    import wx_content_mesh.services.publisher as publisher_module

    uploaded: dict[str, list[str]] = {"inline": [], "cover": []}

    class FakeDraftClient:
        def __init__(self, session, account):
            self.session = session
            self.account = account

        def upload_inline_image(self, image_path: str):
            uploaded["inline"].append(image_path)
            return {"url": f"https://mmbiz.qpic.cn/{Path(image_path).name}"}

        def upload_permanent_image(self, image_path: str):
            uploaded["cover"].append(image_path)
            return {"media_id": "cover_media_1", "url": f"https://mmbiz.qpic.cn/{Path(image_path).name}"}

        def add_draft(self, articles):
            return {"media_id": "draft_1"}

    monkeypatch.setattr(publisher_module, "WeChatApiClient", FakeDraftClient)

    svg_path = tmp_path / "diagram.svg"
    svg_path.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80" viewBox="0 0 120 80">
        <rect width="120" height="80" fill="#ffffff"/>
        <circle cx="40" cy="40" r="24" fill="#4a90e2"/>
        <rect x="68" y="20" width="28" height="40" fill="#43aa8b"/>
        </svg>""",
        encoding="utf-8",
    )

    db = _session()
    account = WeChatAccount(name="main", appid="wx_test", raw_secret="secret")
    db.add(account)
    db.flush()
    article = Article(
        account_id=account.id,
        title="带 SVG 的文章",
        markdown=f"![示意图]({svg_path})",
        cover_source=str(svg_path),
    )
    db.add(article)
    db.flush()

    PublishService(db).create_wechat_draft(article.id, upload_inline_images=True)

    assert article.status == ArticleStatus.draft_created
    assert article.wx_draft_media_id == "draft_1"
    assert uploaded["inline"]
    assert uploaded["cover"]
    assert Path(uploaded["inline"][0]).suffix.lower() == ".png"
    assert Path(uploaded["cover"][0]).suffix.lower() == ".png"


def test_create_wechat_draft_compacts_oversized_html_before_validation(monkeypatch):
    import wx_content_mesh.services.publisher as publisher_module

    captured: dict[str, str] = {}

    class FakeDraftClient:
        def __init__(self, session, account):
            self.session = session
            self.account = account

        def add_draft(self, articles):
            captured["content"] = articles[0]["content"]
            return {"media_id": "draft_oversize_1"}

    monkeypatch.setattr(publisher_module, "WeChatApiClient", FakeDraftClient)

    db = _session()
    account = WeChatAccount(
        name="main",
        appid="wx_test",
        raw_secret="secret",
        default_cover_media_id="cover_media_existing",
    )
    db.add(account)
    db.flush()

    noisy_paragraph = '<p class="body" data-track="abcdefghij" data-origin="klmnopqrst" id="node-123456" style="color:#222">正文</p>'
    html = "<section id='wemd'>" + noisy_paragraph * 230 + "</section>"

    article = Article(
        account_id=account.id,
        title="超长正文",
        markdown="正文",
        html=html,
    )
    db.add(article)
    db.flush()

    PublishService(db).create_wechat_draft(article.id, upload_inline_images=False)

    assert article.status == ArticleStatus.draft_created
    assert article.wx_draft_media_id == "draft_oversize_1"
    assert len(html) >= 20_000
    assert len(captured["content"]) < 20_000
    assert article.meta is not None
    assert article.meta["wechat_draft_compaction"]["applied"] is True


def test_quality_gate_flags_wechat_review_risky_phrases():
    issues = QualityGate().inspect("Claude Agent 协议，为什么它最稳", "这是业界通用最优解，也是更权威的方案。")

    messages = [issue.message for issue in issues]
    assert any("微信内容审核风险表达：最稳" in message for message in messages)
    assert any("微信内容审核风险表达：业界通用最优解" in message for message in messages)
    assert any("微信内容审核风险表达：权威" in message for message in messages)


def test_quality_gate_flags_unrendered_obsidian_and_diagram_sources():
    issues = QualityGate().inspect(
        "图形稿件",
        "这里有 ![[diagram.drawio]]\n\n```graphviz\ndigraph G { A -> B; }\n```",
    )

    messages = [issue.message for issue in issues]
    assert any("最终内容里残留了 Obsidian 内嵌资源语法" in message for message in messages)
    assert any("最终内容里残留了图形源码块" in message for message in messages)


def test_create_wechat_draft_blocks_rendered_obsidian_artifacts(monkeypatch):
    import wx_content_mesh.services.publisher as publisher_module

    class FakeDraftClient:
        def __init__(self, session, account):
            self.session = session
            self.account = account

        def add_draft(self, articles):
            return {"media_id": "draft_should_not_happen"}

    monkeypatch.setattr(publisher_module, "WeChatApiClient", FakeDraftClient)

    db = _session()
    account = WeChatAccount(
        name="main",
        appid="wx_test",
        raw_secret="secret",
        default_cover_media_id="cover_media_existing",
    )
    db.add(account)
    db.flush()

    article = Article(
        account_id=account.id,
        title="残留源码",
        markdown="正文",
        html="<section id='wemd'><p>![[diagram.drawio]]</p></section>",
    )
    db.add(article)
    db.flush()

    try:
        PublishService(db).create_wechat_draft(article.id, upload_inline_images=False)
    except ValueError as exc:
        assert "publish blocked by rendered artifact gate" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("rendered artifact gate should block leaked obsidian syntax")


def test_publish_pending_to_draftbox_blocks_medium_risk_copy(tmp_path: Path):
    db = _session()
    settings = Settings(
        wechat_pending_dir=tmp_path / "pending",
        wechat_draft_dir=tmp_path / "draft",
        wechat_published_backup_dir=tmp_path / "published",
    )
    settings.ensure_dirs()
    settings.wechat_pending_dir.mkdir(parents=True, exist_ok=True)
    pending = settings.wechat_pending_dir / "Claude Agent 协议，为什么它最稳.md"
    pending.write_text("# Claude Agent 协议，为什么它最稳\n\n这是业界通用最优解。", encoding="utf-8")

    try:
        WechatRepoFlowService(settings, db).publish_pending_to_draftbox(
            markdown_path=str(pending),
            account_id=1,
            theme="wechat_baseline",
        )
    except ValueError as exc:
        assert "publish blocked by quality gate" in str(exc)
        assert "微信内容审核风险表达" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("publish should be blocked by quality gate")


def test_create_html_draft_uses_prerendered_html_without_markdown_rerender(monkeypatch, tmp_path: Path):
    import wx_content_mesh.services.publisher as publisher_module

    uploaded: dict[str, list[str]] = {"inline": [], "cover": []}
    captured: dict[str, str] = {}

    class FakeDraftClient:
        def __init__(self, session, account):
            self.session = session
            self.account = account

        def upload_inline_image(self, image_path: str):
            uploaded["inline"].append(image_path)
            return {"url": f"https://mmbiz.qpic.cn/{Path(image_path).name}"}

        def upload_permanent_image(self, image_path: str):
            uploaded["cover"].append(image_path)
            return {"media_id": "cover_media_html", "url": f"https://mmbiz.qpic.cn/{Path(image_path).name}"}

        def add_draft(self, articles):
            captured["content"] = articles[0]["content"]
            captured["digest"] = articles[0]["digest"]
            return {"media_id": "draft_html_1"}

    monkeypatch.setattr(publisher_module, "WeChatApiClient", FakeDraftClient)

    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    inline = asset_dir / "inline.png"
    cover = asset_dir / "cover.png"
    inline.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?"
        b"\x00\x05\xfe\x02\xfeA\xde\xfc\xbb\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    cover.write_bytes(inline.read_bytes())

    db = _session()
    account = WeChatAccount(name="main", appid="wx_test", raw_secret="secret")
    db.add(account)
    db.flush()

    article = PublishService(db).create_html_draft(
        account_id=account.id,
        title="HTML 文章",
        html='''<section id="external" class="editor-shell" data-node="a1">
        <!-- remove me -->
        <h1>Already Rendered</h1>
        <img data-src="inline.png" width="160" />
        </section>''',
        asset_base_dir=str(asset_dir),
        cover_source="cover.png",
        create_local_preview=True,
    )

    assert article.status == ArticleStatus.draft_created
    assert article.markdown == ""
    assert article.theme == "html"
    assert article.wx_draft_media_id == "draft_html_1"
    assert article.local_preview_path
    assert Path(article.local_preview_path).exists()
    assert [str(path) for path in uploaded["inline"]] == [str(inline.resolve())]
    assert [str(path) for path in uploaded["cover"]] == [str(cover.resolve())]
    assert "Already Rendered" in captured["content"]
    assert "theme-wemd_clean" not in captured["content"]
    assert "https://mmbiz.qpic.cn/inline.png" in captured["content"]
    assert "<!-- remove me -->" not in captured["content"]
    assert 'width="160"' not in captured["content"]
    assert 'style="width:160px"' in captured["content"]
    assert captured["digest"] == "Already Rendered"
    assert article.meta is not None
    assert article.meta["content_ingress"] == "html"


def test_create_wechat_draft_uploads_server_rendered_diagram_and_formula_images(monkeypatch):
    import wx_content_mesh.services.publisher as publisher_module

    uploaded: list[str] = []
    captured: dict[str, str] = {}
    downloaded: list[str] = []

    class FakeDraftClient:
        def __init__(self, session, account):
            self.session = session
            self.account = account

        def upload_inline_image(self, image_path: str):
            uploaded.append(image_path)
            return {"url": f"https://mmbiz.qpic.cn/{Path(image_path).name}"}

        def add_draft(self, articles):
            captured["content"] = articles[0]["content"]
            return {"media_id": "draft_diagram_formula_1"}

    monkeypatch.setattr(publisher_module, "WeChatApiClient", FakeDraftClient)

    def fake_download(self, url: str):
        downloaded.append(url)
        safe_name = url.split("/")[-1].split("?")[0] or "asset"
        target = self.settings.upload_dir / f"{safe_name}.png"
        if not target.exists():
            target.write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?"
                b"\x00\x05\xfe\x02\xfeA\xde\xfc\xbb\x00\x00\x00\x00IEND\xaeB`\x82"
            )
        return target

    monkeypatch.setattr(publisher_module.ImageService, "_download", fake_download)

    db = _session()
    account = WeChatAccount(
        name="main",
        appid="wx_test",
        raw_secret="secret",
        default_cover_media_id="cover_media_existing",
    )
    db.add(account)
    db.flush()

    article = Article(
        account_id=account.id,
        title="图形与公式",
        markdown=(
            "```plantuml\nAlice -> Bob: hi\n```\n\n"
            "```mermaid\ngraph TD\nA-->B\n```\n\n"
            "$$\nE = mc^2\n$$\n"
        ),
    )
    db.add(article)
    db.flush()

    PublishService(db).create_wechat_draft(article.id, upload_inline_images=True)

    assert article.status == ArticleStatus.draft_created
    assert article.wx_draft_media_id == "draft_diagram_formula_1"
    assert len(uploaded) >= 1
    assert len(downloaded) == 2
    assert any("kroki.io/plantuml/svg/" in url for url in downloaded)
    assert not any("kroki.io/mermaid/svg/" in url for url in downloaded)
    assert any("latex.codecogs.com/svg.latex?" in url for url in downloaded)
    soup = BeautifulSoup(captured["content"], "html.parser")
    rendered_sources = [img.get("src", "") for img in soup.find_all("img")]
    assert sum(src.startswith("https://mmbiz.qpic.cn/") for src in rendered_sources) >= 2
    assert "graph TD" in captured["content"]


def test_render_article_resolves_obsidian_excalidraw_export_and_uploads_it(monkeypatch, tmp_path: Path):
    import wx_content_mesh.services.publisher as publisher_module

    uploaded: list[str] = []

    class FakeDraftClient:
        def __init__(self, session, account):
            self.session = session
            self.account = account

        def upload_inline_image(self, image_path: str):
            uploaded.append(image_path)
            return {"url": f"https://mmbiz.qpic.cn/{Path(image_path).name}"}

    monkeypatch.setattr(publisher_module, "WeChatApiClient", FakeDraftClient)

    article_dir = tmp_path / "post"
    article_dir.mkdir()
    markdown_path = article_dir / "index.md"
    markdown_path.write_text("图：![[diagram.excalidraw]]", encoding="utf-8")
    exported = article_dir / "diagram.excalidraw.svg"
    exported.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80"><rect width="120" height="80" fill="#fff"/></svg>',
        encoding="utf-8",
    )

    db = _session()
    account = WeChatAccount(name="main", appid="wx_test", raw_secret="secret", default_cover_media_id="cover_media_existing")
    db.add(account)
    db.flush()

    article = Article(
        account_id=account.id,
        title="Obsidian 图",
        markdown=markdown_path.read_text(encoding="utf-8"),
        meta={"source_path": str(markdown_path)},
    )
    db.add(article)
    db.flush()

    rendered = PublishService(db).render_article(article.id, upload_inline_images=True)

    assert rendered.status == ArticleStatus.rendered
    assert uploaded
    assert Path(uploaded[0]).suffix.lower() == ".png"
    assert "https://mmbiz.qpic.cn/" in rendered.html


def test_render_article_resolves_obsidian_drawio_export_and_uploads_it(monkeypatch, tmp_path: Path):
    import wx_content_mesh.services.publisher as publisher_module

    uploaded: list[str] = []

    class FakeDraftClient:
        def __init__(self, session, account):
            self.session = session
            self.account = account

        def upload_inline_image(self, image_path: str):
            uploaded.append(image_path)
            return {"url": f"https://mmbiz.qpic.cn/{Path(image_path).name}"}

    monkeypatch.setattr(publisher_module, "WeChatApiClient", FakeDraftClient)

    article_dir = tmp_path / "post"
    article_dir.mkdir()
    markdown_path = article_dir / "index.md"
    markdown_path.write_text("图：![[diagram.drawio|320]]", encoding="utf-8")
    exported = article_dir / "diagram.drawio.svg"
    exported.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80"><rect width="120" height="80" fill="#fff"/></svg>',
        encoding="utf-8",
    )

    db = _session()
    account = WeChatAccount(name="main", appid="wx_test", raw_secret="secret", default_cover_media_id="cover_media_existing")
    db.add(account)
    db.flush()

    article = Article(
        account_id=account.id,
        title="Obsidian drawio 图",
        markdown=markdown_path.read_text(encoding="utf-8"),
        meta={"source_path": str(markdown_path)},
    )
    db.add(article)
    db.flush()

    rendered = PublishService(db).render_article(article.id, upload_inline_images=True)

    assert rendered.status == ArticleStatus.rendered
    assert uploaded
    assert Path(uploaded[0]).suffix.lower() == ".png"
    assert "https://mmbiz.qpic.cn/" in rendered.html
