from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
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
)
from .services.publisher import PublishService
from .services.quality_gate import QualityGate
from .services.xhs_exporter import XhsExporter

app = FastAPI(title="wx-content-mesh", version="0.2.0")


@app.on_event("startup")
def startup() -> None:
    init_db()


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
