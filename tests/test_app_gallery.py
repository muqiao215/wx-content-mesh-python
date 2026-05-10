from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from wx_content_mesh.app import app, get_db
from wx_content_mesh.db import Base
from wx_content_mesh.models import Article, WeChatAccount


def _session():
    engine = create_engine("sqlite:///:memory:", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def test_theme_gallery_page_lists_new_themes_and_article_content():
    db = _session()
    account = WeChatAccount(name="main", appid="wx_test", raw_secret="secret")
    db.add(account)
    db.flush()
    article = Article(account_id=account.id, title="画廊测试", markdown="## 小节\n\n正文 **重点**")
    db.add(article)
    db.flush()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        response = client.get(f"/preview/themes?article_id={article.id}")
    finally:
        app.dependency_overrides.clear()
        db.close()

    assert response.status_code == 200
    assert "Theme Gallery" in response.text
    assert "academic_paper" in response.text
    assert "knowledge_base" in response.text
    assert "morandi_forest" in response.text
    assert "wechat_baseline" in response.text
    assert "画廊测试" in response.text
    assert "正文" in response.text
