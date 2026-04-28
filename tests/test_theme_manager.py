from wx_content_mesh.services.theme_manager import ThemeManager


SAMPLE_CSS = """
#wemd {
  --color-primary: #123456;
  color: var(--color-primary);
}

#wemd h2 + p {
  margin-top: 4px;
}
"""


def test_theme_manager_imports_css_and_metadata(tmp_path):
    manager = ThemeManager(theme_dir=tmp_path, metadata_path=tmp_path / "metadata.json")

    info = manager.import_css(
        name="custom_theme",
        css=SAMPLE_CSS,
        display_name="Custom Theme",
        description="Imported CSS template",
        source="test",
        tags=["custom", "css"],
    )

    assert info.name == "custom_theme"
    assert (tmp_path / "custom_theme.css").exists()
    assert info.metadata.display_name == "Custom Theme"
    assert info.metadata.tags == ["custom", "css"]

    themes = manager.list_themes()
    assert [theme.name for theme in themes] == ["custom_theme"]


def test_theme_manager_rejects_bad_names_and_empty_css(tmp_path):
    manager = ThemeManager(theme_dir=tmp_path, metadata_path=tmp_path / "metadata.json")

    try:
        manager.import_css(name="../bad", css=SAMPLE_CSS)
    except ValueError as exc:
        assert "theme name" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("bad theme name should fail")

    try:
        manager.import_css(name="bad_css", css="body {")
    except ValueError as exc:
        assert "compileable" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("bad CSS should fail")
