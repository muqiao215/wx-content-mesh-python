from fastapi.testclient import TestClient

import qiao_wechat.app as app_module
from qiao_wechat.services.theme_manager import ThemeManager


SAMPLE_CSS = """
#wemd {
  color: #123456;
}

#wemd .card strong {
  color: #654321;
}
"""


def test_theme_api_imports_lists_and_updates_metadata(tmp_path, monkeypatch):
    manager = ThemeManager(theme_dir=tmp_path, metadata_path=tmp_path / "metadata.json")
    monkeypatch.setattr(app_module, "ThemeManager", lambda: manager)

    client = TestClient(app_module.app)
    imported = client.post(
        "/themes/import",
        json={
            "name": "api_theme",
            "css": SAMPLE_CSS,
            "display_name": "API Theme",
            "description": "Imported through API",
            "source": "test",
            "tags": ["api"],
        },
    )

    assert imported.status_code == 200
    assert imported.json()["metadata"]["display_name"] == "API Theme"

    listed = client.get("/themes")
    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "api_theme"

    css = client.get("/themes/api_theme/css")
    assert css.status_code == 200
    assert "#wemd .card strong" in css.text

    updated = client.put(
        "/themes/api_theme/metadata",
        json={"display_name": "Renamed Theme", "preview_cover": "/static/theme.png"},
    )
    assert updated.status_code == 200
    assert updated.json()["metadata"]["display_name"] == "Renamed Theme"
    assert updated.json()["metadata"]["preview_cover"] == "/static/theme.png"
