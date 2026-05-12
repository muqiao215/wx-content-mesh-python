from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import Settings
from .publisher import PublishService
from .quality_gate import QualityGate


@dataclass(frozen=True)
class RepoArticle:
    title: str
    path: Path
    chars: int
    bucket: str


class WechatRepoFlowService:
    def __init__(self, settings: Settings, session: Session):
        self.settings = settings
        self.session = session
        self.publisher = PublishService(session)
        self.quality_gate = QualityGate()

    def list_drafts(self) -> list[RepoArticle]:
        return self._list_markdown_files(self.settings.wechat_draft_dir, bucket="draft")

    def list_pending(self) -> list[RepoArticle]:
        return self._list_markdown_files(self.settings.wechat_pending_dir, bucket="pending")

    def move_draft_to_pending(self, markdown_path: str, *, copy_only: bool = False) -> Path:
        source = self._ensure_inside(markdown_path, self.settings.wechat_draft_dir)
        target = self.settings.wechat_pending_dir / source.name
        if target.exists():
            raise ValueError(f"pending article already exists: {target}")
        if copy_only:
            shutil.copy2(source, target)
        else:
            shutil.move(str(source), str(target))
        return target

    def publish_pending_to_draftbox(
        self,
        *,
        markdown_path: str,
        account_id: int,
        author: str | None = None,
        digest: str | None = None,
        cover: str | None = None,
        theme: str = "wechat_baseline",
    ) -> tuple[int, str]:
        source = self._ensure_inside(markdown_path, self.settings.wechat_pending_dir)
        markdown = source.read_text(encoding="utf-8")
        title = self._extract_title(markdown, fallback=source.stem)[:32]
        issues = self.quality_gate.inspect(title, markdown)
        blocking = [issue for issue in issues if issue.level in {"high", "medium"}]
        if blocking:
            summary = "；".join(f"{issue.message} -> {issue.suggestion}" for issue in blocking)
            raise ValueError(f"publish blocked by quality gate: {summary}")
        article = self.publisher.create_article(
            account_id=account_id,
            title=title,
            markdown=markdown,
            author=author,
            digest=digest,
            cover_source=cover,
            content_source_url=None,
            theme=theme,
        )
        article.meta = {**(article.meta or {}), "source_path": str(source)}
        self.session.flush()
        article = self.publisher.create_wechat_draft(article.id)
        self.session.flush()
        return article.id, article.wx_draft_media_id or ""

    def archive_pending_after_publish(self, markdown_path: str) -> Path:
        source = self._ensure_inside(markdown_path, self.settings.wechat_pending_dir)
        target = self.settings.wechat_published_backup_dir / source.name
        if target.exists():
            raise ValueError(f"published backup already exists: {target}")
        shutil.move(str(source), str(target))
        return target

    def _list_markdown_files(self, directory: Path, *, bucket: str) -> list[RepoArticle]:
        root = directory.resolve()
        if not root.exists():
            return []
        result: list[RepoArticle] = []
        for path in sorted(root.glob("*.md")):
            text = path.read_text(encoding="utf-8", errors="ignore").strip()
            if not text:
                continue
            result.append(
                RepoArticle(
                    title=path.stem,
                    path=path,
                    chars=len(text),
                    bucket=bucket,
                )
            )
        return result

    @staticmethod
    def _ensure_inside(markdown_path: str, base_dir: Path) -> Path:
        source = Path(markdown_path).expanduser().resolve()
        root = base_dir.resolve()
        if not source.exists() or not source.is_file():
            raise ValueError(f"markdown not found: {source}")
        try:
            source.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"{source} is not inside {root}") from exc
        return source

    @staticmethod
    def _extract_title(markdown: str, *, fallback: str) -> str:
        match = re.search(r'(?m)^title:\s*["\']?(.*?)["\']?\s*$', markdown)
        if match and match.group(1).strip():
            return match.group(1).strip()
        first_heading = re.search(r"(?m)^#\s+(.+?)\s*$", markdown)
        if first_heading and first_heading.group(1).strip():
            return first_heading.group(1).strip()
        return fallback
