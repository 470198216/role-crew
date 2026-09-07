from __future__ import annotations

from typing import Any

from role_crew.config import Settings


class LLMNotConfigured(RuntimeError):
    """第一版不调模型。配好通用 API Key 后再启用。"""


class LLMClient:
    """OpenAI 兼容 chat 占位。第一版只检查配置，不发请求。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def ready(self) -> bool:
        key = self.settings.llm_api_key
        return bool(key) and not key.startswith("sk-xxx") and not key.startswith("sk-sp-")

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        raise LLMNotConfigured(
            "LLM 尚未接入。先用 `role-crew demo` 跑信封和执行器；"
            "下一版把 LLM_API_KEY 写成百炼/DeepSeek 的通用 sk- 密钥后再跑 `role-crew run`。"
        )
