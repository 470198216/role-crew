from __future__ import annotations

import time
from typing import Any

import httpx

from role_crew.config import Settings


class LLMNotConfigured(RuntimeError):
    """密钥或入口未配好。"""


class LLMError(RuntimeError):
    """调用失败。"""


class LLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def ready(self) -> bool:
        key = self.settings.llm_api_key.strip()
        url = self.settings.llm_base_url.lower()
        if not key or key in {"sk-xxx", "sk-your-key-here"}:
            return False
        if key.startswith("sk-sp-") and "token-plan" not in url and "coding" not in url:
            return False
        return True

    def ready_or_raise(self) -> None:
        key = self.settings.llm_api_key.strip()
        url = self.settings.llm_base_url
        if not key or key in {"sk-xxx", "sk-your-key-here"}:
            raise LLMNotConfigured("LLM_API_KEY 为空。复制 .env.example 为 .env 后填写。")
        if key.startswith("sk-sp-") and "token-plan" not in url.lower() and "coding" not in url.lower():
            raise LLMNotConfigured(
                "sk-sp- 是 Token Plan / Coding Plan 专属密钥，"
                "LLM_BASE_URL 必须是 token-plan.cn-beijing.maas.aliyuncs.com "
                "（或 coding.dashscope），不能打普通 dashscope 看图入口。"
            )

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        self.ready_or_raise()
        payload: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 2048,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        url = self.settings.llm_base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        last_error = ""
        for attempt in range(5):
            try:
                with httpx.Client(timeout=90.0) as client:
                    resp = client.post(url, headers=headers, json=payload)
            except httpx.ConnectError as exc:
                raise LLMError(f"连不上 {url}: {exc}") from exc

            if resp.status_code == 429:
                last_error = resp.text[:400]
                time.sleep(2 ** attempt)
                continue
            if resp.status_code >= 400:
                raise LLMError(f"LLM HTTP {resp.status_code}: {resp.text[:800]}")

            data = resp.json()
            try:
                msg = data["choices"][0]["message"]
            except (KeyError, IndexError, TypeError) as exc:
                raise LLMError("返回格式异常") from exc
            if not isinstance(msg, dict):
                raise LLMError("message 不是对象")
            time.sleep(1.2)
            return msg
        raise LLMError(f"LLM HTTP 429 多次重试仍失败: {last_error}")
