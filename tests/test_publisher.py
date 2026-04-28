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
