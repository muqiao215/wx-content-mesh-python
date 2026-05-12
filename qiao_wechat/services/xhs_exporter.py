from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Article, JobStatus, PublishChannel, PublishJob


class XhsExporter:
    """Safe 小红书 path: export a publish package instead of bypassing platform login.

    You can later add a compliant OpenAPI/MCP adapter around this output.
    """

    def __init__(self, session: Session):
        self.session = session
        self.settings = get_settings()

    def export_article(self, article_id: int, *, tags: Iterable[str] = ()) -> Path:
        article = self.session.get(Article, article_id)
        if not article:
            raise KeyError(f"article not found: {article_id}")
        note = self._to_note(article.markdown, article.title, tags=tags)
        out_dir = self.settings.output_dir / f"article_{article.id}" / "xhs"
        out_dir.mkdir(parents=True, exist_ok=True)
        note_path = out_dir / "note.txt"
        note_path.write_text(note, encoding="utf-8")
        article.xhs_note = note
        self.session.add(
            PublishJob(
                article_id=article.id,
                account_id=article.account_id,
                channel=PublishChannel.xhs_export,
                status=JobStatus.success,
                response_json={"path": str(note_path)},
            )
        )
        self.session.flush()
        return note_path

    @staticmethod
    def _to_note(markdown: str, title: str, *, tags: Iterable[str]) -> str:
        text = markdown
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
        text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
        text = re.sub(r"[*_`>~-]", "", text)
        text = BeautifulSoup(text, "html.parser").get_text("\n")
        chunks = [line.strip() for line in text.splitlines() if line.strip()]
        body = "\n\n".join(chunks[:12])
        if len(body) > 900:
            body = body[:880].rstrip() + "……"
        tag_text = " ".join("#" + t.strip().lstrip("#") for t in tags if t.strip())
        return f"{title}\n\n{body}\n\n{tag_text}".strip() + "\n"
