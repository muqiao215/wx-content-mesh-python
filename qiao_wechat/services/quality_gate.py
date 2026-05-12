from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class QualityIssue:
    level: str
    message: str
    suggestion: str


class QualityGate:
    """Simple content gate for originality, evidence and publish readiness.

    This is not a detector-evasion module. It flags risky patterns before publishing.
    """

    banned_intents = ["洗稿", "绕过检测", "对抗检测器", "去AI味检测", "规避平台审核"]
    weak_phrases = ["众所周知", "毋庸置疑", "值得一提的是", "总而言之", "在当今时代"]
    wechat_review_risky_phrases = [
        "最优解",
        "业界通用最优解",
        "最稳",
        "权威",
        "绝对",
        "唯一正确",
        "必须",
        "确保",
    ]
    leaked_render_artifact_patterns = [
        (re.compile(r"!\[\[[^\]]+\]\]"), "最终内容里残留了 Obsidian 内嵌资源语法"),
        (re.compile(r"\[!(?:[A-Z][A-Z0-9_-]*)\]", re.I), "最终内容里残留了 Obsidian callout 标记"),
        (re.compile(r"```(?:plantuml|graphviz|dot|mermaid|excalidraw|drawio)\b", re.I), "最终内容里残留了图形源码块"),
    ]

    def inspect(self, title: str, markdown: str) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        full = f"{title}\n{markdown}"
        for word in self.banned_intents:
            if word in full:
                issues.append(QualityIssue("high", f"出现不合规意图词：{word}", "改为原创增强、事实核验、编辑润色。"))
        for phrase in self.weak_phrases:
            if phrase in full:
                issues.append(QualityIssue("low", f"套话偏多：{phrase}", "替换成具体场景、数据、经验或案例。"))
        if len(markdown) < 600:
            issues.append(QualityIssue("medium", "正文过短", "公众号长文建议补充案例、证据和清晰结论。"))
        if not re.search(r"https?://|来源|参考|数据|报告", markdown):
            issues.append(QualityIssue("medium", "缺少来源/依据痕迹", "至少保留参考链接、数据来源或人工事实核验说明。"))
        if len(title) > 32:
            issues.append(QualityIssue("medium", "标题超过微信草稿常用限制", "控制在 32 字以内。"))
        for phrase in self.wechat_review_risky_phrases:
            if phrase in full:
                issues.append(
                    QualityIssue(
                        "medium",
                        f"微信内容审核风险表达：{phrase}",
                        "改成更克制的经验判断，例如“更稳”“常见做法”“更适合当前工程约束”。",
                    )
                )
        for pattern, message in self.leaked_render_artifact_patterns:
            if pattern.search(markdown):
                issues.append(
                    QualityIssue(
                        "medium",
                        message,
                        "先把残留的 Obsidian 或图形源码转换掉，确认最终 HTML 只保留正文和图片。",
                    )
                )
        return issues
