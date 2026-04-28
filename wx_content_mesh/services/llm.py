from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class LLMConfig:
    base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    api_key: str | None = os.getenv("OPENAI_API_KEY")
    model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    timeout: float = 60.0


class LLMClient:
    """Tiny OpenAI-compatible client. If no API key exists, returns deterministic drafts."""

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()

    def chat(self, system: str, user: str) -> str:
        if not self.config.api_key:
            return self._fallback(user)
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.7,
        }
        resp = requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {self.config.api_key}"},
            timeout=self.config.timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    @staticmethod
    def _fallback(user: str) -> str:
        return (
            "## 需要人工补充的版本\n\n"
            "这是一个本地占位输出。请配置 OPENAI_API_KEY 后获得真实多智能体结果。\n\n"
            "### 输入摘要\n\n"
            + user[:1200]
        )
