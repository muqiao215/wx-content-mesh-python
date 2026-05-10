from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Article, ArticleStatus, JobStatus, MediaAsset, PublishChannel, PublishJob, WeChatAccount
from .html_normalizer import HtmlNormalizer
from .image_service import ImageService
from .renderer import WeChatMarkdownRenderer
from .wechat_client import WeChatApiClient, WeChatError


class PublishService:
    def __init__(self, session: Session):
        self.session = session
        self.settings = get_settings()
        self.image_service = ImageService(session)
        self.html_normalizer = HtmlNormalizer()

    def create_article(self, **kwargs: Any) -> Article:
        article = Article(**kwargs)
        self.session.add(article)
        self.session.flush()
        return article

    def create_html_draft(
        self,
        *,
        account_id: int,
        title: str,
        html: str,
        asset_base_dir: str | None = None,
        author: str | None = None,
        digest: str | None = None,
        cover_source: str | None = None,
        content_source_url: str | None = None,
        meta: dict[str, Any] | None = None,
        upload_inline_images: bool = True,
        force_reupload_cover: bool = False,
        create_local_preview: bool = True,
    ) -> Article:
        account = self.session.get(WeChatAccount, account_id)
        if not account:
            raise KeyError(f"wechat account not found: {account_id}")
        if not html.strip():
            raise ValueError("html is required")

        article_meta = {**(meta or {}), "content_ingress": "html"}
        if asset_base_dir:
            article_meta["asset_base_dir"] = str(Path(asset_base_dir).expanduser().resolve())

        article = self.create_article(
            account_id=account_id,
            title=title,
            markdown="",
            html=html,
            author=author,
            digest=digest,
            cover_source=cover_source,
            content_source_url=content_source_url,
            theme="html",
            meta=article_meta,
        )
        self.prepare_html_article(
            article.id,
            upload_inline_images=upload_inline_images,
            create_local_preview=create_local_preview,
        )
        return self.create_wechat_draft(
            article.id,
            upload_inline_images=False,
            force_reupload_cover=force_reupload_cover,
        )

    def create_html_file_draft(
        self,
        *,
        account_id: int,
        html_path: str,
        title: str | None = None,
        asset_base_dir: str | None = None,
        author: str | None = None,
        digest: str | None = None,
        cover_source: str | None = None,
        content_source_url: str | None = None,
        meta: dict[str, Any] | None = None,
        upload_inline_images: bool = True,
        force_reupload_cover: bool = False,
        create_local_preview: bool = True,
    ) -> Article:
        path = Path(html_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise ValueError(f"html file not found: {path}")

        html = path.read_text(encoding="utf-8")
        final_title = title or path.stem[:32]
        final_asset_base_dir = asset_base_dir or str(path.parent)
        article_meta = {**(meta or {}), "source_html_path": str(path)}

        return self.create_html_draft(
            account_id=account_id,
            title=final_title,
            html=html,
            asset_base_dir=final_asset_base_dir,
            author=author,
            digest=digest,
            cover_source=cover_source,
            content_source_url=content_source_url,
            meta=article_meta,
            upload_inline_images=upload_inline_images,
            force_reupload_cover=force_reupload_cover,
            create_local_preview=create_local_preview,
        )

    def prepare_html_article(
        self,
        article_id: int,
        *,
        upload_inline_images: bool = True,
        create_local_preview: bool = True,
    ) -> Article:
        article = self._article(article_id)
        if not article.html:
            raise ValueError("article.html is required")
        html = self.html_normalizer.normalize(article.html)
        article.html = html
        if upload_inline_images:
            account = self._require_account(article)
            client = WeChatApiClient(self.session, account)
            html = WeChatMarkdownRenderer().replace_image_sources(
                html,
                lambda src: self._upload_inline(account, client, src, base_dir=self._resolve_asset_base_dir(article)),
            )
            article.html = html
        if create_local_preview:
            out = self.settings.output_dir / f"article_{article.id}" / "wechat_preview.html"
            WeChatMarkdownRenderer().save_preview(html, out, page_title=article.title)
            article.local_preview_path = str(out)
            article.meta = {**(article.meta or {}), "local_preview_url": f"{self.settings.app_base_url}/preview/article/{article.id}"}
            self._job(article, PublishChannel.local_preview, JobStatus.success, response={"path": str(out)})
        article.status = ArticleStatus.rendered
        self.session.flush()
        return article

    def render_article(self, article_id: int, *, theme: str | None = None, upload_inline_images: bool = False) -> Article:
        article = self._article(article_id)
        theme_name = theme or article.theme or self.settings.render_theme
        renderer = WeChatMarkdownRenderer(theme_name=theme_name)
        html = renderer.render(article.markdown, title=article.title)
        if upload_inline_images:
            account = self._require_account(article)
            client = WeChatApiClient(self.session, account)
            markdown_dir = self._resolve_markdown_dir(article)
            html = renderer.replace_image_sources(html, lambda src: self._upload_inline(account, client, src, base_dir=markdown_dir))
        out = self.settings.output_dir / f"article_{article.id}" / "wechat_preview.html"
        renderer.save_preview(html, out, page_title=article.title)
        article.html = html
        article.theme = theme_name
        article.local_preview_path = str(out)
        article.status = ArticleStatus.rendered
        article.meta = {**(article.meta or {}), "local_preview_url": f"{self.settings.app_base_url}/preview/article/{article.id}"}
        self._job(article, PublishChannel.local_preview, JobStatus.success, response={"path": str(out)})
        self.session.flush()
        return article

    def create_wechat_draft(self, article_id: int, *, upload_inline_images: bool = True, force_reupload_cover: bool = False) -> Article:
        article = self._article(article_id)
        account = self._require_account(article)
        client = WeChatApiClient(self.session, account)
        if not article.html or upload_inline_images:
            self.render_article(article_id, upload_inline_images=upload_inline_images)
            self.session.flush()
            article = self._article(article_id)
        cover_media_id = self._ensure_cover_media_id(article, account, client, force_reupload=force_reupload_cover)
        wx_article = {
            "article_type": "news",
            "title": article.title[:32],
            "thumb_media_id": cover_media_id,
            "author": (article.author or account.author or self.settings.default_author or "")[:16],
            "digest": (article.digest or self._auto_digest(article.markdown or article.html or ""))[:128],
            "content": self._prepare_wechat_draft_content(article, article.html),
            "content_source_url": (article.content_source_url or "")[:1024],
            "need_open_comment": 0,
            "only_fans_can_comment": 0,
        }
        self._validate_draft_content(wx_article["content"])
        job = self._job(article, PublishChannel.wx_draft, JobStatus.running, request={"articles": [{**wx_article, "content": "<omitted>"}]})
        try:
            payload = client.add_draft([wx_article])
            media_id = payload["media_id"]
            article.wx_draft_media_id = media_id
            article.status = ArticleStatus.draft_created
            job.status = JobStatus.success
            job.response_json = payload
            job.finished_at = _utcnow_naive()
        except Exception as exc:
            article.status = ArticleStatus.failed
            job.status = JobStatus.failed
            job.error_message = str(exc)
            if isinstance(exc, WeChatError):
                job.response_json = exc.payload
            job.finished_at = _utcnow_naive()
            raise
        self.session.flush()
        return article

    def send_preview(self, article_id: int, *, touser_openid: str | None = None, towxname: str | None = None) -> dict[str, Any]:
        self._require_preview_enabled()
        article = self._article(article_id)
        account = self._require_account(article)
        if not article.wx_draft_media_id:
            self.create_wechat_draft(article_id)
            self.session.flush()
            article = self._article(article_id)
        client = WeChatApiClient(self.session, account)
        job = self._job(article, PublishChannel.wx_preview, JobStatus.running, request={"touser": bool(touser_openid), "towxname": towxname})
        try:
            payload = client.preview_mpnews(article.wx_draft_media_id, touser_openid=touser_openid, towxname=towxname)
            article.status = ArticleStatus.preview_sent
            job.status = JobStatus.success
            job.response_json = payload
            job.finished_at = _utcnow_naive()
            self.session.flush()
            return payload
        except Exception as exc:
            job.status = JobStatus.failed
            job.error_message = str(exc)
            if isinstance(exc, WeChatError):
                job.response_json = exc.payload
            job.finished_at = _utcnow_naive()
            self.session.flush()
            raise

    def submit_freepublish(self, article_id: int) -> Article:
        self._require_publish_enabled()
        article = self._article(article_id)
        account = self._require_account(article)
        if not article.wx_draft_media_id:
            self.create_wechat_draft(article_id)
            self.session.flush()
            article = self._article(article_id)
        client = WeChatApiClient(self.session, account)
        job = self._job(article, PublishChannel.wx_freepublish, JobStatus.running, request={"media_id": article.wx_draft_media_id})
        try:
            payload = client.submit_freepublish(article.wx_draft_media_id)
            article.wx_publish_id = payload.get("publish_id")
            if not article.wx_publish_id:
                raise ValueError("WeChat freepublish response did not return publish_id")
            article.status = ArticleStatus.publish_submitted
            job.status = JobStatus.success
            job.response_json = payload
            job.finished_at = _utcnow_naive()
        except Exception as exc:
            article.status = ArticleStatus.failed
            job.status = JobStatus.failed
            job.error_message = str(exc)
            if isinstance(exc, WeChatError):
                job.response_json = exc.payload
            job.finished_at = _utcnow_naive()
            raise
        self.session.flush()
        return article

    def poll_publish_status(self, article_id: int) -> dict[str, Any]:
        article = self._article(article_id)
        account = self._require_account(article)
        if not article.wx_publish_id:
            raise ValueError("article has no wx_publish_id")
        client = WeChatApiClient(self.session, account)
        payload = client.get_publish_status(article.wx_publish_id)
        status = payload.get("publish_status")
        article_id_from_wx = payload.get("article_id") or payload.get("article_detail", {}).get("article_id")
        if article_id_from_wx:
            article.wx_article_id = str(article_id_from_wx)
        article_url = self._article_url_from_publish_status(payload)
        if article_url:
            article.wx_article_url = article_url
        normalized = str(status)
        if normalized == "0" or (status is None and article_id_from_wx):
            article.status = ArticleStatus.published
            if not article.wx_article_url:
                self._hydrate_published_url(article, client)
        elif normalized in {"2", "3", "4", "5", "6"}:
            article.status = ArticleStatus.failed
        self._job(
            article,
            PublishChannel.wx_freepublish,
            JobStatus.failed if article.status == ArticleStatus.failed else JobStatus.success,
            response=payload,
        )
        self.session.flush()
        return payload

    def _hydrate_published_url(self, article: Article, client: WeChatApiClient) -> None:
        if not article.wx_article_id:
            return
        try:
            detail = client.get_published_article(article.wx_article_id)
        except Exception:
            return
        # Common shapes: {'news_item': [{'url': '...'}]} or nested article_detail.
        url = None
        if isinstance(detail.get("news_item"), list) and detail["news_item"]:
            url = detail["news_item"][0].get("article_url")
        if not url:
            url = detail.get("article_url")
        if url:
            article.wx_article_url = url

    def _ensure_cover_media_id(self, article: Article, account: WeChatAccount, client: WeChatApiClient, *, force_reupload: bool) -> str:
        if article.cover_media_id and not force_reupload:
            return article.cover_media_id
        if account.default_cover_media_id and not article.cover_source and not force_reupload:
            article.cover_media_id = account.default_cover_media_id
            return account.default_cover_media_id
        if not article.cover_source:
            raise ValueError("cover_source or account.default_cover_media_id is required for WeChat draft")
        cover_source = self._resolve_image_source(article, article.cover_source)
        asset, blob = self.image_service.prepare_asset_for_wechat(account_id=account.id, source=cover_source, purpose="cover")
        if asset.media_id and not force_reupload:
            article.cover_media_id = asset.media_id
            return asset.media_id
        payload = client.upload_permanent_image(blob.path)
        asset.media_id = payload.get("media_id")
        asset.wx_url = payload.get("url")
        asset.raw_response = payload
        if not asset.media_id:
            raise ValueError("WeChat cover upload did not return media_id")
        article.cover_media_id = asset.media_id
        return asset.media_id

    def _upload_inline(self, account: WeChatAccount, client: WeChatApiClient, src: str, *, base_dir: Path | None = None) -> str:
        from urllib.parse import unquote
        decoded = unquote(src)
        resolved = decoded
        if base_dir and not decoded.startswith(("http://", "https://", "/")):
            candidate = (base_dir / Path(decoded)).resolve()
            if candidate.exists():
                resolved = str(candidate)
        asset, blob = self.image_service.prepare_asset_for_wechat(account_id=account.id, source=resolved, purpose="inline")
        if asset.wx_url:
            return asset.wx_url
        payload = client.upload_inline_image(blob.path)
        asset.wx_url = payload.get("url")
        asset.raw_response = payload
        if not asset.wx_url:
            raise ValueError("WeChat inline image upload did not return url")
        self.session.flush()
        return asset.wx_url

    @staticmethod
    def _auto_digest(markdown: str) -> str:
        if "<" in markdown and ">" in markdown:
            html_text = BeautifulSoup(markdown, "html.parser").get_text(" ")
            html_text = " ".join(html_text.split())
            if html_text:
                return html_text[:100]
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", markdown)
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
        text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
        text = re.sub(r"[*_`>~-]", "", text)
        text = BeautifulSoup(text, "html.parser").get_text(" ")
        text = " ".join(text.split())
        if not text:
            text = markdown.replace("#", "").strip()
        return text[:100]

    @staticmethod
    def _validate_draft_content(content: str | None) -> None:
        if not content:
            raise ValueError("WeChat draft content is required")
        if len(content) >= 20_000:
            raise ValueError("WeChat draft content must be under 20000 characters")
        if len(content.encode("utf-8")) >= 1 * 1024 * 1024:
            raise ValueError("WeChat draft content must be under 1MB")

    def _prepare_wechat_draft_content(self, article: Article, content: str | None) -> str:
        if not content:
            self._validate_draft_content(content)
            return content or ""

        original_chars = len(content)
        original_bytes = len(content.encode("utf-8"))
        optimized = content
        applied = False

        if original_chars >= 20_000 or original_bytes >= 1 * 1024 * 1024:
            candidate = self._compact_wechat_html(content)
            if len(candidate) < original_chars or len(candidate.encode("utf-8")) < original_bytes:
                optimized = candidate
                applied = True

        meta = {**(article.meta or {})}
        meta["wechat_draft_compaction"] = {
            "applied": applied,
            "original_chars": original_chars,
            "final_chars": len(optimized),
            "original_bytes": original_bytes,
            "final_bytes": len(optimized.encode("utf-8")),
        }
        article.meta = meta

        self._validate_draft_content(optimized)
        return optimized

    @staticmethod
    def _compact_wechat_html(content: str) -> str:
        return HtmlNormalizer().compact(content)

    @staticmethod
    def _article_url_from_publish_status(payload: dict[str, Any]) -> str | None:
        detail = payload.get("article_detail")
        if not isinstance(detail, dict):
            return None
        items = detail.get("item")
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict):
                return first.get("article_url")
        return None

    def _article(self, article_id: int) -> Article:
        article = self.session.get(Article, article_id)
        if not article:
            raise KeyError(f"article not found: {article_id}")
        return article

    def _require_account(self, article: Article) -> WeChatAccount:
        if not article.account_id:
            raise ValueError("article.account_id is required for WeChat publishing")
        account = self.session.get(WeChatAccount, article.account_id)
        if not account:
            raise KeyError(f"wechat account not found: {article.account_id}")
        return account

    @staticmethod
    def _resolve_markdown_dir(article: Article) -> Path | None:
        meta = article.meta or {}
        source = meta.get("source_path")
        if source:
            p = Path(source)
            if p.is_file():
                return p.parent
        return None

    @staticmethod
    def _resolve_asset_base_dir(article: Article) -> Path | None:
        meta = article.meta or {}
        source = meta.get("asset_base_dir")
        if source:
            return Path(source)
        return PublishService._resolve_markdown_dir(article)

    @staticmethod
    def _resolve_image_source(article: Article, source: str) -> str:
        if source.startswith(("http://", "https://", "/")):
            return source
        base_dir = PublishService._resolve_asset_base_dir(article)
        if not base_dir:
            return source
        candidate = (base_dir / Path(source)).resolve()
        if candidate.exists():
            return str(candidate)
        return source

    def _require_preview_enabled(self) -> None:
        if self.settings.allow_wechat_preview:
            return
        raise ValueError(
            "WeChat phone preview is disabled. "
            "Set WCM_ALLOW_WECHAT_PREVIEW=true only after confirming the account has message/mass/preview permission. "
            "Personal unverified accounts should stay in local-preview + draftbox mode."
        )

    def _require_publish_enabled(self) -> None:
        if self.settings.allow_wechat_publish:
            return
        raise ValueError(
            "WeChat freepublish submit is disabled. "
            "Set WCM_ALLOW_WECHAT_PUBLISH=true only after confirming the account has the required publish permission. "
            "Personal unverified accounts should stay in draftbox mode."
        )

    def _job(
        self,
        article: Article,
        channel: PublishChannel,
        status: JobStatus,
        *,
        request: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
    ) -> PublishJob:
        job = PublishJob(
            article_id=article.id,
            account_id=article.account_id,
            channel=channel,
            status=status,
            request_json=request,
            response_json=response,
            started_at=_utcnow_naive() if status == JobStatus.running else None,
            finished_at=_utcnow_naive() if status in (JobStatus.success, JobStatus.failed) else None,
        )
        self.session.add(job)
        self.session.flush()
        return job


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
