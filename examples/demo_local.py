from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qiao_wechat.db import db_session, init_db
from qiao_wechat.services.publisher import PublishService
from qiao_wechat.services.xhs_exporter import XhsExporter

init_db()
md = Path(__file__).with_name("sample_article.md").read_text(encoding="utf-8")
with db_session() as db:
    service = PublishService(db)
    article = service.create_article(
        title="wxAiPost 应该怎么借鉴，而不是照搬",
        markdown=md,
        theme="wemd_card",
    )
    article = service.render_article(article.id)
    xhs_path = XhsExporter(db).export_article(article.id, tags=["公众号排版", "内容自动化", "Python"])
    print("article_id:", article.id)
    print("preview:", article.local_preview_path)
    print("xhs:", xhs_path)
