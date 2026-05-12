from pathlib import Path

from qiao_wechat.cli import build_parser


def test_html_draft_parser_accepts_html_file_args(tmp_path: Path):
    html_path = tmp_path / "article.html"
    html_path.write_text("<section><p>正文</p></section>", encoding="utf-8")

    parser = build_parser()
    args = parser.parse_args(
        [
            "html-draft",
            "--account-id",
            "1",
            "--html",
            str(html_path),
            "--title",
            "已渲染文章",
            "--asset-base-dir",
            str(tmp_path),
            "--cover",
            str(tmp_path / "cover.png"),
            "--no-upload-inline-images",
            "--force-reupload-cover",
            "--no-local-preview",
        ]
    )

    assert args.account_id == 1
    assert args.html == str(html_path)
    assert args.title == "已渲染文章"
    assert args.asset_base_dir == str(tmp_path)
    assert args.cover == str(tmp_path / "cover.png")
    assert args.no_upload_inline_images is True
    assert args.force_reupload_cover is True
    assert args.no_local_preview is True
