from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .llm import LLMClient


@dataclass
class CreativeBrief:
    topic: str
    audience: str = "公众号和小红书读者"
    angle: str = "实用、具体、有案例"
    materials: list[str] | None = None
    keywords: list[str] | None = None


@dataclass
class CreativeResult:
    research: str
    article_markdown: str
    audit: str
    visual_plan: str
    xhs_note: str


class SequentialCreativePipeline:
    """Researcher -> Writer -> Auditor -> Designer pipeline in Python.

    It is CrewAI-compatible in shape, but has zero CrewAI dependency. Replace LLMClient
    with your own model gateway or wrap these steps as CrewAI tasks.
    """

    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()

    def run(self, brief: CreativeBrief) -> CreativeResult:
        research = self.research(brief)
        article = self.write(brief, research)
        audit = self.audit(brief, article)
        visual = self.design(brief, article)
        xhs_note = self.xhs_transform(brief, article)
        return CreativeResult(research, article, audit, visual, xhs_note)

    def research(self, brief: CreativeBrief) -> str:
        return self.llm.chat(
            "你是内容研究员，只输出可用于写作的事实、角度、反例和风险，不写成文。",
            f"主题：{brief.topic}\n受众：{brief.audience}\n角度：{brief.angle}\n关键词：{brief.keywords or []}\n素材：{brief.materials or []}",
        )

    def write(self, brief: CreativeBrief, research: str) -> str:
        return self.llm.chat(
            "你是公众号作者。写成 Markdown，结构要有节奏，避免空话；结尾给可执行清单。",
            f"主题：{brief.topic}\n受众：{brief.audience}\n研究资料：\n{research}",
        )

    def audit(self, brief: CreativeBrief, article: str) -> str:
        return self.llm.chat(
            "你是审稿人。只输出问题清单：事实、版权、平台风险、结构、标题。",
            f"主题：{brief.topic}\n文章：\n{article}",
        )

    def design(self, brief: CreativeBrief, article: str) -> str:
        return self.llm.chat(
            "你是视觉设计师。输出封面建议、正文配图位置、小红书卡片拆分建议。",
            f"主题：{brief.topic}\n文章：\n{article[:4000]}",
        )

    def xhs_transform(self, brief: CreativeBrief, article: str) -> str:
        return self.llm.chat(
            "你是小红书编辑。把长文改成 700 字内笔记，保留观点，不夸大，不伪造经历。",
            f"主题：{brief.topic}\n长文：\n{article[:5000]}",
        )
