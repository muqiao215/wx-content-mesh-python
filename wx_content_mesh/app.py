from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session

from .db import SessionLocal, init_db
from .models import Article, PublishJob, WeChatAccount
from .schemas import (
    AccountCreate,
    AccountOut,
    ArticleCreate,
    ArticleOut,
    DraftRequest,
    JobOut,
    PreviewRequest,
    PublishRequest,
    RenderRequest,
    ThemeImportRequest,
    ThemeMetadataUpdate,
    ThemeOut,
)
from .services.publisher import PublishService
from .services.quality_gate import QualityGate
from .services.theme_gallery import ThemeGalleryService
from .services.theme_manager import ThemeManager, theme_info_to_dict
from .services.xhs_exporter import XhsExporter

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="wx-content-mesh", version="0.2.0", lifespan=lifespan)


def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/accounts/wechat", response_model=AccountOut)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)) -> WeChatAccount:
    account = WeChatAccount(**payload.model_dump())
    db.add(account)
    db.flush()
    return account


@app.get("/accounts/wechat", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db)) -> list[WeChatAccount]:
    return db.query(WeChatAccount).order_by(WeChatAccount.id.desc()).all()


@app.post("/articles", response_model=ArticleOut)
def create_article(payload: ArticleCreate, db: Session = Depends(get_db)) -> Article:
    issues = QualityGate().inspect(payload.title, payload.markdown)
    article = PublishService(db).create_article(**payload.model_dump())
    article.meta = {**(article.meta or {}), "quality_issues": [issue.__dict__ for issue in issues]}
    db.flush()
    return article


@app.get("/articles", response_model=list[ArticleOut])
def list_articles(account_id: int | None = None, db: Session = Depends(get_db)) -> list[Article]:
    query = db.query(Article)
    if account_id is not None:
        query = query.filter(Article.account_id == account_id)
    return query.order_by(Article.id.desc()).limit(100).all()


@app.get("/articles/{article_id}", response_model=ArticleOut)
def get_article(article_id: int, db: Session = Depends(get_db)) -> Article:
    article = db.get(Article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@app.get("/articles/{article_id}/jobs", response_model=list[JobOut])
def list_article_jobs(article_id: int, db: Session = Depends(get_db)) -> list[PublishJob]:
    article = db.get(Article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return db.query(PublishJob).filter(PublishJob.article_id == article_id).order_by(PublishJob.id.desc()).all()


@app.get("/jobs", response_model=list[JobOut])
def list_jobs(channel: str | None = None, db: Session = Depends(get_db)) -> list[PublishJob]:
    query = db.query(PublishJob)
    if channel:
        query = query.filter(PublishJob.channel == channel)
    return query.order_by(PublishJob.id.desc()).limit(100).all()


@app.post("/articles/{article_id}/render", response_model=ArticleOut)
def render_article(article_id: int, payload: RenderRequest, db: Session = Depends(get_db)) -> Article:
    try:
        return PublishService(db).render_article(article_id, theme=payload.theme, upload_inline_images=payload.upload_inline_images)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/preview/article/{article_id}")
def preview_article(article_id: int, db: Session = Depends(get_db)):
    article = db.get(Article, article_id)
    if not article or not article.local_preview_path:
        raise HTTPException(status_code=404, detail="preview not found; render article first")
    path = Path(article.local_preview_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="preview file missing")
    return FileResponse(path, media_type="text/html")


@app.get("/preview/themes", response_class=HTMLResponse)
def preview_themes(article_id: int | None = None, db: Session = Depends(get_db)) -> HTMLResponse:
    return HTMLResponse(ThemeGalleryService(db).build_page(article_id=article_id))


@app.get("/themes", response_model=list[ThemeOut])
def list_themes() -> list[dict]:
    return [theme_info_to_dict(info) for info in ThemeManager().list_themes()]


@app.get("/themes/{theme_name}/css", response_class=PlainTextResponse)
def get_theme_css(theme_name: str) -> PlainTextResponse:
    try:
        path = ThemeManager().get_css(theme_name)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/css")


@app.post("/themes/import", response_model=ThemeOut)
def import_theme(payload: ThemeImportRequest) -> dict:
    try:
        info = ThemeManager().import_css(
            name=payload.name,
            css=payload.css,
            display_name=payload.display_name,
            description=payload.description or "",
            source=payload.source or "user",
            source_url=payload.source_url,
            preview_cover=payload.preview_cover,
            tags=payload.tags,
            overwrite=payload.overwrite,
        )
        return theme_info_to_dict(info)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/themes/import-file", response_model=ThemeOut)
async def import_theme_file(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    display_name: str | None = Form(default=None),
    description: str = Form(default=""),
    source: str = Form(default="user"),
    source_url: str | None = Form(default=None),
    preview_cover: str | None = Form(default=None),
    tags: str = Form(default=""),
    overwrite: bool = Form(default=False),
) -> dict:
    raw = await file.read()
    theme_name = name or Path(file.filename or "").stem
    parsed_tags = [part.strip() for part in tags.split(",") if part.strip()]
    try:
        info = ThemeManager().import_css(
            name=theme_name,
            css=raw.decode("utf-8-sig"),
            display_name=display_name,
            description=description,
            source=source,
            source_url=source_url,
            preview_cover=preview_cover,
            tags=parsed_tags,
            overwrite=overwrite,
        )
        return theme_info_to_dict(info)
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="theme CSS file must be UTF-8") from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/themes/{theme_name}/metadata", response_model=ThemeOut)
def update_theme_metadata(theme_name: str, payload: ThemeMetadataUpdate) -> dict:
    try:
        info = ThemeManager().update_metadata(
            theme_name,
            display_name=payload.display_name,
            description=payload.description,
            source=payload.source,
            source_url=payload.source_url,
            preview_cover=payload.preview_cover,
            tags=payload.tags,
        )
        return theme_info_to_dict(info)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/articles/{article_id}/wechat/draft", response_model=ArticleOut)
def create_draft(article_id: int, payload: DraftRequest, db: Session = Depends(get_db)) -> Article:
    try:
        return PublishService(db).create_wechat_draft(
            article_id,
            upload_inline_images=payload.upload_inline_images,
            force_reupload_cover=payload.force_reupload_cover,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/articles/{article_id}/wechat/preview")
def send_preview(article_id: int, payload: PreviewRequest, db: Session = Depends(get_db)):
    try:
        return PublishService(db).send_preview(article_id, touser_openid=payload.touser_openid, towxname=payload.towxname)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/articles/{article_id}/wechat/publish", response_model=ArticleOut)
def publish(article_id: int, payload: PublishRequest, db: Session = Depends(get_db)) -> Article:
    service = PublishService(db)
    try:
        if payload.mode == "draft":
            return service.create_wechat_draft(article_id)
        if payload.mode == "preview":
            if not payload.preview:
                raise ValueError("preview payload is required")
            service.send_preview(article_id, touser_openid=payload.preview.touser_openid, towxname=payload.preview.towxname)
            return db.get(Article, article_id)
        if payload.mode == "freepublish":
            return service.submit_freepublish(article_id)
        if payload.mode == "poll":
            service.poll_publish_status(article_id)
            return db.get(Article, article_id)
        if payload.mode == "full_safe":
            service.create_wechat_draft(article_id)
            if payload.preview:
                service.send_preview(article_id, touser_openid=payload.preview.touser_openid, towxname=payload.preview.towxname)
            return db.get(Article, article_id)
        raise ValueError(f"unsupported mode: {payload.mode}")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/articles/{article_id}/wechat/poll")
def poll(article_id: int, db: Session = Depends(get_db)):
    try:
        return PublishService(db).poll_publish_status(article_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/articles/{article_id}/xhs/export")
def export_xhs(article_id: int, tags: str = "", db: Session = Depends(get_db)):
    try:
        path = XhsExporter(db).export_article(article_id, tags=[t.strip() for t in tags.split(",") if t.strip()])
        return {"path": str(path)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
