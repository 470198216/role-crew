from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
ROLES_DIR = ROOT / "roles"
CONFIG_DIR = ROOT / "configs"
WORKSPACE_DIR = ROOT / "workspace"
TRACE_DIR = ROOT / "traces"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_base_url: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1", alias="LLM_BASE_URL")
    llm_model: str = Field(default="qwen-plus", alias="LLM_MODEL")
    max_agent_steps: int = Field(default=12, alias="MAX_AGENT_STEPS")
    max_peer_depth: int = Field(default=2, alias="MAX_PEER_DEPTH")

    @field_validator("llm_api_key", "llm_base_url", "llm_model", mode="before")
    @classmethod
    def _strip_env(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML 根必须是映射: {path}")
    return data
