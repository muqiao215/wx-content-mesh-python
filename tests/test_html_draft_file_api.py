from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import wx_content_mesh.app as app_module
from wx_content_mesh.db import Base
from wx_content_mesh.models import WeChatAccount


def test_create_draft_from_html_file_endpoint(monkeypatch, tmp_path: Path):
    import wx_content_mesh.services.publisher as publisher_module

    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_db():
        db = Session()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    class FakeDraftClient:
        def __init__(self, session, account):
            self.session = session
            self.account = account

        def add_draft(self, articles):
            return {"media_id": "draft_from_file_api"}

    monkeypatch.setattr(publisher_module, "WeChatApiClient", FakeDraftClient)

    html_path = tmp_path / "final.html"
    html_path.write_text("<section><p>文件正文</p></section>", encoding="utf-8")

    with Session() as db:
        account = WeChatAccount(
            name="main",
            appid="wx_test",
            raw_secret="secret",
            default_cover_media_id="cover_existing",
        )
        db.add(account)
        db.commit()
        account_id = account.id

    app_module.app.dependency_overrides[app_module.get_db] = override_db
    try:
        client = TestClient(app_module.app)
        response = client.post(
            "/wechat/drafts/from-html-file",
            json={
                "account_id": account_id,
                "html_path": str(html_path),
                "options": {"upload_inline_images": False, "create_local_preview": False},
            },
        )
    finally:
        app_module.app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "draft_created"
    assert payload["title"] == "final"
    assert payload["wx_draft_media_id"] == "draft_from_file_api"
    assert payload["meta"]["content_ingress"] == "html"
    assert payload["meta"]["source_html_path"] == str(html_path.resolve())
