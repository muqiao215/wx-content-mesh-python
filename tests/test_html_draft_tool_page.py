from fastapi.testclient import TestClient

from qiao_wechat.app import app


def test_html_draft_tool_page_renders_form():
    client = TestClient(app)
    response = client.get("/tools/html-draft")

    assert response.status_code == 200
    assert "HTML To WeChat Draft" in response.text
    assert "/wechat/drafts/from-html" in response.text
    assert "微信公众号 HTML" in response.text
    assert "刷新账号列表" in response.text
