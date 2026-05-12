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
    HtmlDraftCreate,
    HtmlDraftFileCreate,
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


app = FastAPI(title="wx-content-mesh", version="0.3.0", lifespan=lifespan)


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


@app.get("/tools/html-draft", response_class=HTMLResponse)
def html_draft_tool() -> HTMLResponse:
    page = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>wx-content-mesh HTML Draft Tool</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f3f6fb;
      --panel: #ffffff;
      --panel-alt: #f8fafc;
      --border: #dbe3ef;
      --text: #132033;
      --muted: #5b6b82;
      --primary: #2563eb;
      --primary-soft: #dbeafe;
      --success: #166534;
      --success-soft: #dcfce7;
      --danger: #b91c1c;
      --danger-soft: #fee2e2;
      --shadow: 0 18px 45px rgba(15, 23, 42, 0.08);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: linear-gradient(180deg, #eef4ff 0%, var(--bg) 220px);
      color: var(--text);
    }
    main {
      max-width: 1120px;
      margin: 0 auto;
      padding: 28px 20px 40px;
    }
    .shell {
      display: grid;
      grid-template-columns: minmax(0, 2fr) minmax(300px, 1fr);
      gap: 20px;
      align-items: start;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      box-shadow: var(--shadow);
    }
    .hero {
      margin-bottom: 20px;
      padding: 22px 24px;
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      box-shadow: var(--shadow);
    }
    .hero h1 {
      margin: 0 0 8px;
      font-size: 22px;
      line-height: 1.2;
    }
    .hero p {
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
    }
    form { padding: 22px 24px 24px; }
    .section-title {
      margin: 0 0 14px;
      font-size: 14px;
      color: var(--muted);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px 16px;
      margin-bottom: 20px;
    }
    .field,
    .field-wide {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .field-wide { margin-bottom: 16px; }
    label {
      font-size: 13px;
      font-weight: 600;
      color: var(--text);
    }
    input,
    select,
    textarea {
      width: 100%;
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #fff;
      color: var(--text);
      font: inherit;
    }
    input:focus,
    select:focus,
    textarea:focus {
      outline: none;
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
    }
    textarea {
      min-height: 132px;
      resize: vertical;
    }
    #html {
      min-height: 420px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      line-height: 1.5;
    }
    #meta {
      min-height: 110px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      line-height: 1.5;
    }
    .checks {
      display: grid;
      gap: 10px;
      margin: 18px 0 24px;
    }
    .check {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel-alt);
    }
    .check input {
      width: 16px;
      height: 16px;
      margin: 0;
      padding: 0;
    }
    .actions {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 8px;
    }
    button {
      border: 0;
      border-radius: 8px;
      padding: 11px 16px;
      background: var(--primary);
      color: #fff;
      font: inherit;
      font-weight: 600;
      cursor: pointer;
    }
    button.secondary {
      background: #e5edf9;
      color: #173153;
    }
    button:disabled {
      opacity: 0.55;
      cursor: not-allowed;
    }
    .side {
      padding: 22px 24px 24px;
      display: grid;
      gap: 16px;
    }
    .hint {
      margin: 0;
      padding: 12px 14px;
      border-radius: 8px;
      background: var(--panel-alt);
      color: var(--muted);
      line-height: 1.5;
      border: 1px solid var(--border);
    }
    .status {
      padding: 12px 14px;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: var(--panel-alt);
      color: var(--muted);
      line-height: 1.5;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .status.success {
      color: var(--success);
      background: var(--success-soft);
      border-color: #bbf7d0;
    }
    .status.error {
      color: var(--danger);
      background: var(--danger-soft);
      border-color: #fecaca;
    }
    .kv {
      display: grid;
      gap: 10px;
      padding: 14px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel-alt);
    }
    .kv div {
      display: flex;
      justify-content: space-between;
      gap: 14px;
      font-size: 13px;
    }
    .kv span:first-child { color: var(--muted); }
    .kv span:last-child {
      text-align: right;
      overflow-wrap: anywhere;
    }
    .hidden { display: none; }
    @media (max-width: 920px) {
      .shell { grid-template-columns: 1fr; }
      .grid { grid-template-columns: 1fr; }
      main { padding-inline: 14px; }
      .hero, form, .side { padding-inline: 18px; }
    }
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <h1>HTML To WeChat Draft</h1>
      <p>把高完成度微信公众号 HTML 直接送进本地草稿链路。页面只负责组包和调用接口，图片上传、封面处理、草稿创建都在后端完成。</p>
    </section>

    <div class="shell">
      <section class="panel">
        <form id="draft-form">
          <p class="section-title">Draft Payload</p>

          <div class="grid">
            <div class="field">
              <label for="account_id">公众号账号</label>
              <select id="account_id"></select>
            </div>
            <div class="field">
              <label for="title">标题</label>
              <input id="title" name="title" maxlength="32" required placeholder="输入草稿标题">
            </div>
            <div class="field">
              <label for="author">作者</label>
              <input id="author" name="author" placeholder="可选">
            </div>
            <div class="field">
              <label for="digest">摘要</label>
              <input id="digest" name="digest" maxlength="128" placeholder="可选，留空则后端自动提取">
            </div>
            <div class="field">
              <label for="cover_source">封面路径或 URL</label>
              <input id="cover_source" name="cover_source" placeholder="/abs/path/cover.png 或 https://...">
            </div>
            <div class="field">
              <label for="asset_base_dir">资源基目录</label>
              <input id="asset_base_dir" name="asset_base_dir" placeholder="/abs/path/to/assets">
            </div>
            <div class="field-wide" style="grid-column: 1 / -1;">
              <label for="content_source_url">来源链接</label>
              <input id="content_source_url" name="content_source_url" placeholder="可选">
            </div>
          </div>

          <div class="field-wide">
            <label for="html">微信公众号 HTML</label>
            <textarea id="html" name="html" required placeholder="<section><p>...</p></section>"></textarea>
          </div>

          <div class="field-wide">
            <label for="meta">扩展元数据（JSON，可选）</label>
            <textarea id="meta" name="meta" placeholder="{&quot;source_kind&quot;:&quot;external_html&quot;}"></textarea>
          </div>

          <div class="checks">
            <label class="check">
              <input id="upload_inline_images" type="checkbox" checked>
              <span>重写并上传正文图片</span>
            </label>
            <label class="check">
              <input id="create_local_preview" type="checkbox" checked>
              <span>生成本地预览文件</span>
            </label>
            <label class="check">
              <input id="force_reupload_cover" type="checkbox">
              <span>强制重新上传封面</span>
            </label>
          </div>

          <div class="actions">
            <button id="submit" type="submit">创建微信草稿</button>
            <button id="reload" class="secondary" type="button">刷新账号列表</button>
          </div>
        </form>
      </section>

      <aside class="panel side">
        <p class="section-title">Run Status</p>
        <p class="hint">这页不是新的工作流中心，只是给 HTML-first 草稿入口一个可操作前台。适合把外部视觉项目产出的最终 HTML 快速送入草稿箱。</p>
        <div id="status" class="status">等待提交。</div>
        <div id="result" class="kv hidden">
          <div><span>Article ID</span><span id="result-article-id">-</span></div>
          <div><span>Status</span><span id="result-status">-</span></div>
          <div><span>Draft Media ID</span><span id="result-draft-id">-</span></div>
          <div><span>Theme</span><span id="result-theme">-</span></div>
          <div><span>Preview</span><span id="result-preview">-</span></div>
        </div>
      </aside>
    </div>
  </main>

  <script>
    const accountSelect = document.getElementById('account_id')
    const form = document.getElementById('draft-form')
    const statusBox = document.getElementById('status')
    const resultBox = document.getElementById('result')
    const submitButton = document.getElementById('submit')
    const reloadButton = document.getElementById('reload')

    function setStatus(message, tone) {
      statusBox.textContent = message
      statusBox.className = 'status' + (tone ? ' ' + tone : '')
    }

    function setResult(article) {
      resultBox.classList.remove('hidden')
      document.getElementById('result-article-id').textContent = article.id ?? '-'
      document.getElementById('result-status').textContent = article.status ?? '-'
      document.getElementById('result-draft-id').textContent = article.wx_draft_media_id ?? '-'
      document.getElementById('result-theme').textContent = article.theme ?? '-'

      const previewUrl = article.meta && article.meta.local_preview_url
      const previewCell = document.getElementById('result-preview')
      previewCell.textContent = ''
      if (previewUrl) {
        const link = document.createElement('a')
        link.href = previewUrl
        link.target = '_blank'
        link.rel = 'noreferrer noopener'
        link.textContent = 'Open preview'
        previewCell.appendChild(link)
      } else {
        previewCell.textContent = '-'
      }
    }

    async function loadAccounts() {
      setStatus('正在加载账号列表…')
      accountSelect.innerHTML = '<option value="">加载中…</option>'
      try {
        const response = await fetch('/accounts/wechat')
        const accounts = await response.json()
        if (!response.ok) {
          throw new Error(accounts.detail || response.statusText)
        }
        if (!accounts.length) {
          accountSelect.innerHTML = '<option value="">暂无账号</option>'
          setStatus('没有可用账号，先去 /docs 或 API 创建账号。', 'error')
          return
        }
        accountSelect.innerHTML = accounts.map(account => {
          const label = [account.name, account.appid, account.author || '']
            .filter(Boolean)
            .join(' · ')
          return '<option value=\"' + account.id + '\">' + label + '</option>'
        }).join('')
        setStatus('账号列表已加载。')
      } catch (error) {
        accountSelect.innerHTML = '<option value="">加载失败</option>'
        setStatus('账号列表加载失败：' + error.message, 'error')
      }
    }

    function parseMeta() {
      const raw = document.getElementById('meta').value.trim()
      if (!raw) return null
      try {
        return JSON.parse(raw)
      } catch (error) {
        throw new Error('meta JSON 解析失败')
      }
    }

    form.addEventListener('submit', async event => {
      event.preventDefault()
      resultBox.classList.add('hidden')
      submitButton.disabled = true
      reloadButton.disabled = true

      try {
        const payload = {
          account_id: Number(accountSelect.value),
          title: document.getElementById('title').value.trim(),
          html: document.getElementById('html').value,
          author: document.getElementById('author').value.trim() || null,
          digest: document.getElementById('digest').value.trim() || null,
          cover_source: document.getElementById('cover_source').value.trim() || null,
          asset_base_dir: document.getElementById('asset_base_dir').value.trim() || null,
          content_source_url: document.getElementById('content_source_url').value.trim() || null,
          meta: parseMeta(),
          options: {
            upload_inline_images: document.getElementById('upload_inline_images').checked,
            create_local_preview: document.getElementById('create_local_preview').checked,
            force_reupload_cover: document.getElementById('force_reupload_cover').checked
          }
        }

        if (!payload.account_id) {
          throw new Error('请选择公众号账号')
        }
        if (!payload.title) {
          throw new Error('标题不能为空')
        }
        if (!payload.html.trim()) {
          throw new Error('HTML 不能为空')
        }

        setStatus('正在创建微信草稿…')

        const response = await fetch('/wechat/drafts/from-html', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
        const result = await response.json()
        if (!response.ok) {
          throw new Error(result.detail || response.statusText)
        }
        setResult(result)
        setStatus('草稿创建成功。', 'success')
      } catch (error) {
        setStatus(String(error.message || error), 'error')
      } finally {
        submitButton.disabled = false
        reloadButton.disabled = false
      }
    })

    reloadButton.addEventListener('click', loadAccounts)
    loadAccounts()
  </script>
</body>
</html>"""
    return HTMLResponse(page)


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


@app.post("/wechat/drafts/from-html", response_model=ArticleOut)
def create_draft_from_html(payload: HtmlDraftCreate, db: Session = Depends(get_db)) -> Article:
    try:
        return PublishService(db).create_html_draft(
            account_id=payload.account_id,
            title=payload.title,
            html=payload.html,
            asset_base_dir=payload.asset_base_dir,
            author=payload.author,
            digest=payload.digest,
            cover_source=payload.cover_source,
            content_source_url=payload.content_source_url,
            meta=payload.meta,
            upload_inline_images=payload.options.upload_inline_images,
            force_reupload_cover=payload.options.force_reupload_cover,
            create_local_preview=payload.options.create_local_preview,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/wechat/drafts/from-html-file", response_model=ArticleOut)
def create_draft_from_html_file(payload: HtmlDraftFileCreate, db: Session = Depends(get_db)) -> Article:
    try:
        return PublishService(db).create_html_file_draft(
            account_id=payload.account_id,
            html_path=payload.html_path,
            title=payload.title,
            asset_base_dir=payload.asset_base_dir,
            author=payload.author,
            digest=payload.digest,
            cover_source=payload.cover_source,
            content_source_url=payload.content_source_url,
            meta=payload.meta,
            upload_inline_images=payload.options.upload_inline_images,
            force_reupload_cover=payload.options.force_reupload_cover,
            create_local_preview=payload.options.create_local_preview,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
