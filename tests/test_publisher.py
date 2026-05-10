from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from wx_content_mesh.db import Base
from wx_content_mesh.models import Article, ArticleStatus, WeChatAccount
from wx_content_mesh.services.publisher import PublishService


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
