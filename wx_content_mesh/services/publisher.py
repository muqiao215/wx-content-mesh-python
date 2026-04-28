from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Article, ArticleStatus, JobStatus, MediaAsset, PublishChannel, PublishJob, WeChatAccount
from .image_service import ImageService
from .renderer import WeChatMarkdownRenderer
from .wechat_client import WeChatApiClient, WeChatError


class PublishService:
    def __init__(self, session: Session):
        self.session = session
        self.settings = get_settings()
        self.image_service = ImageService(session)

    def create_article(self, **kwargs: Any) -> Article:
        article = Article(**kwargs)
        self.session.add(article)
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
            html = renderer.replace_image_sources(html, lambda src: self._upload_inline(account, client, src))
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
            "digest": (article.digest or self._auto_digest(article.markdown))[:128],
            "content": article.html,
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
        asset, blob = self.image_service.materialize_asset(account_id=account.id, source=article.cover_source, purpose="cover")
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

    def _upload_inline(self, account: WeChatAccount, client: WeChatApiClient, src: str) -> str:
        asset, blob = self.image_service.materialize_asset(account_id=account.id, source=src, purpose="inline")
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
