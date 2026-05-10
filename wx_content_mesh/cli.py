from __future__ import annotations

import argparse
from pathlib import Path

from .db import db_session, init_db
from .models import Article, PublishJob, WeChatAccount
from .services.publisher import PublishService
from .services.quality_gate import QualityGate
from .services.xhs_exporter import XhsExporter


def cmd_init(_: argparse.Namespace) -> None:
    init_db()
    print("database initialized")


def cmd_add_account(args: argparse.Namespace) -> None:
    init_db()
    with db_session() as db:
        account = WeChatAccount(
            name=args.name,
            appid=args.appid,
            raw_secret=args.secret,
            secret_env_name=args.secret_env_name,
            account_type=args.account_type,
            is_certified=args.certified,
            author=args.author,
            default_cover_media_id=args.default_cover_media_id,
        )
        db.add(account)
        db.flush()
        print(f"created account id={account.id} name={account.name}")


def cmd_create_article(args: argparse.Namespace) -> None:
    init_db()
    md_path = Path(args.markdown).resolve()
    markdown = md_path.read_text(encoding="utf-8")
    with db_session() as db:
        article = PublishService(db).create_article(
            account_id=args.account_id,
            title=args.title,
            markdown=markdown,
            author=args.author,
            digest=args.digest,
            cover_source=args.cover,
            content_source_url=args.content_source_url,
            theme=args.theme,
        )
        article.meta = {**(article.meta or {}), "source_path": str(md_path)}
        db.flush()
        print(f"created article id={article.id}")


def cmd_list_articles(args: argparse.Namespace) -> None:
    init_db()
    with db_session() as db:
        query = db.query(Article)
        if args.account_id is not None:
            query = query.filter(Article.account_id == args.account_id)
        for article in query.order_by(Article.id.desc()).limit(args.limit).all():
            print(f"{article.id}\t{article.status.value}\taccount={article.account_id or '-'}\t{article.title}")


def cmd_inspect(args: argparse.Namespace) -> None:
    init_db()
    with db_session() as db:
        article = db.get(Article, args.article_id)
        if not article:
            raise SystemExit(f"article not found: {args.article_id}")
        issues = QualityGate().inspect(article.title, article.markdown)
        article.meta = {**(article.meta or {}), "quality_issues": [issue.__dict__ for issue in issues]}
        db.flush()
        if not issues:
            print("no quality issues")
            return
        for issue in issues:
            print(f"[{issue.level}] {issue.message} -> {issue.suggestion}")


def cmd_render(args: argparse.Namespace) -> None:
    init_db()
    with db_session() as db:
        article = PublishService(db).render_article(args.article_id, theme=args.theme, upload_inline_images=args.upload_inline_images)
        print(article.local_preview_path)


def cmd_draft(args: argparse.Namespace) -> None:
    init_db()
    with db_session() as db:
        article = PublishService(db).create_wechat_draft(args.article_id, upload_inline_images=not args.no_upload_inline_images)
        print(f"draft media_id={article.wx_draft_media_id}")


def cmd_html_draft(args: argparse.Namespace) -> None:
    init_db()
    with db_session() as db:
        article = PublishService(db).create_html_file_draft(
            account_id=args.account_id,
            html_path=args.html,
            title=args.title,
            asset_base_dir=args.asset_base_dir,
            author=args.author,
            digest=args.digest,
            cover_source=args.cover,
            content_source_url=args.content_source_url,
            meta=None,
            upload_inline_images=not args.no_upload_inline_images,
            force_reupload_cover=args.force_reupload_cover,
            create_local_preview=not args.no_local_preview,
        )
        print(f"article_id={article.id}")
        print(f"draft media_id={article.wx_draft_media_id}")


def cmd_preview(args: argparse.Namespace) -> None:
    init_db()
    with db_session() as db:
        payload = PublishService(db).send_preview(args.article_id, touser_openid=args.openid, towxname=args.wxname)
        print(payload)


def cmd_publish(args: argparse.Namespace) -> None:
    init_db()
    with db_session() as db:
        article = PublishService(db).submit_freepublish(args.article_id)
        print(f"publish_id={article.wx_publish_id}")


def cmd_poll(args: argparse.Namespace) -> None:
    init_db()
    with db_session() as db:
        payload = PublishService(db).poll_publish_status(args.article_id)
        print(payload)


def cmd_jobs(args: argparse.Namespace) -> None:
    init_db()
    with db_session() as db:
        query = db.query(PublishJob)
        if args.article_id is not None:
            query = query.filter(PublishJob.article_id == args.article_id)
        for job in query.order_by(PublishJob.id.desc()).limit(args.limit).all():
            err = f" error={job.error_message}" if job.error_message else ""
            print(f"{job.id}\tarticle={job.article_id}\t{job.channel.value}\t{job.status.value}{err}")


def cmd_xhs(args: argparse.Namespace) -> None:
    init_db()
    with db_session() as db:
        path = XhsExporter(db).export_article(args.article_id, tags=args.tags or [])
        print(path)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wx-content-mesh")
    sub = p.add_subparsers(required=True)

    s = sub.add_parser("init")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("add-account")
    s.add_argument("--name", required=True)
    s.add_argument("--appid", required=True)
    s.add_argument("--secret")
    s.add_argument("--secret-env-name")
    s.add_argument("--account-type", default="unknown", choices=["subscription", "service", "unknown"])
    s.add_argument("--certified", action="store_true")
    s.add_argument("--author", default="")
    s.add_argument("--default-cover-media-id")
    s.set_defaults(func=cmd_add_account)

    s = sub.add_parser("create-article")
    s.add_argument("--account-id", type=int)
    s.add_argument("--title", required=True)
    s.add_argument("--markdown", required=True)
    s.add_argument("--cover")
    s.add_argument("--author")
    s.add_argument("--digest")
    s.add_argument("--content-source-url")
    s.add_argument("--theme", default="wemd_clean")
    s.set_defaults(func=cmd_create_article)

    s = sub.add_parser("list-articles")
    s.add_argument("--account-id", type=int)
    s.add_argument("--limit", type=int, default=50)
    s.set_defaults(func=cmd_list_articles)

    s = sub.add_parser("inspect")
    s.add_argument("article_id", type=int)
    s.set_defaults(func=cmd_inspect)

    s = sub.add_parser("render")
    s.add_argument("article_id", type=int)
    s.add_argument("--theme")
    s.add_argument("--upload-inline-images", action="store_true")
    s.set_defaults(func=cmd_render)

    s = sub.add_parser("draft")
    s.add_argument("article_id", type=int)
    s.add_argument("--no-upload-inline-images", action="store_true")
    s.set_defaults(func=cmd_draft)

    s = sub.add_parser("html-draft")
    s.add_argument("--account-id", type=int, required=True)
    s.add_argument("--html", required=True)
    s.add_argument("--title")
    s.add_argument("--asset-base-dir")
    s.add_argument("--cover")
    s.add_argument("--author")
    s.add_argument("--digest")
    s.add_argument("--content-source-url")
    s.add_argument("--no-upload-inline-images", action="store_true")
    s.add_argument("--force-reupload-cover", action="store_true")
    s.add_argument("--no-local-preview", action="store_true")
    s.set_defaults(func=cmd_html_draft)

    s = sub.add_parser("preview")
    s.add_argument("article_id", type=int)
    s.add_argument("--openid")
    s.add_argument("--wxname")
    s.set_defaults(func=cmd_preview)

    s = sub.add_parser("publish")
    s.add_argument("article_id", type=int)
    s.set_defaults(func=cmd_publish)

    s = sub.add_parser("poll")
    s.add_argument("article_id", type=int)
    s.set_defaults(func=cmd_poll)

    s = sub.add_parser("jobs")
    s.add_argument("--article-id", type=int)
    s.add_argument("--limit", type=int, default=50)
    s.set_defaults(func=cmd_jobs)

    s = sub.add_parser("xhs-export")
    s.add_argument("article_id", type=int)
    s.add_argument("--tags", nargs="*", default=[])
    s.set_defaults(func=cmd_xhs)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
