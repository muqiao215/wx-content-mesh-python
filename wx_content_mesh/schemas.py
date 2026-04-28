from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .models import AccountStatus, AccountType, ArticleStatus, JobStatus, PublishChannel


class AccountCreate(BaseModel):
    name: str
    appid: str
    raw_secret: str | None = None
    secret_env_name: str | None = None
    account_type: AccountType = AccountType.unknown
    is_certified: bool = False
    author: str | None = None
    default_cover_media_id: str | None = None
    remark: str | None = None


class AccountOut(BaseModel):
    id: int
    name: str
    appid: str
    account_type: AccountType
    is_certified: bool
    author: str | None
    default_cover_media_id: str | None
    status: AccountStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class ArticleCreate(BaseModel):
    account_id: int | None = None
    title: str = Field(max_length=32)
    markdown: str
    author: str | None = None
    digest: str | None = Field(default=None, max_length=128)
    cover_source: str | None = None
    content_source_url: str | None = None
    theme: str = "wemd_clean"
    meta: dict[str, Any] | None = None


class ArticleOut(BaseModel):
    id: int
    account_id: int | None
    title: str
    status: ArticleStatus
    theme: str
    local_preview_path: str | None
    wx_draft_media_id: str | None
    wx_publish_id: str | None
    wx_article_id: str | None
    wx_article_url: str | None
    meta: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RenderRequest(BaseModel):
    theme: str | None = None
    upload_inline_images: bool = False


class DraftRequest(BaseModel):
    upload_inline_images: bool = True
    force_reupload_cover: bool = False


class PreviewRequest(BaseModel):
    # WeChat preview sends a message to the specified user; it does not return a public URL.
    touser_openid: str | None = None
    towxname: str | None = None


class PublishRequest(BaseModel):
    mode: Literal["draft", "preview", "freepublish", "poll", "full_safe"] = "draft"
    preview: PreviewRequest | None = None


class JobOut(BaseModel):
    id: int
    article_id: int
    account_id: int | None
    channel: PublishChannel
    status: JobStatus
    request_json: dict[str, Any] | None
    response_json: dict[str, Any] | None
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ThemeMetadataUpdate(BaseModel):
    display_name: str | None = None
    description: str | None = None
    source: str | None = None
    source_url: str | None = None
    preview_cover: str | None = None
    tags: list[str] | None = None


class ThemeImportRequest(ThemeMetadataUpdate):
    name: str
    css: str
    overwrite: bool = False


class ThemeMetadataOut(BaseModel):
    name: str
    display_name: str
    description: str
    source: str
    source_url: str | None
    preview_cover: str | None
    tags: list[str]
    built_in: bool
    created_at: str | None
    updated_at: str | None


class ThemeOut(BaseModel):
    name: str
    css_path: str
    css_size: int
    metadata: ThemeMetadataOut
