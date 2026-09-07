from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1"
Status = Literal["continue", "need_peer", "verified", "failed"]


class EvidenceItem(BaseModel):
    tool: str
    ok: bool
    summary: str = ""


class Handoff(BaseModel):
    to: str
    task: str


class Envelope(BaseModel):
    """所有角色共用的交接信封。没有 evidence 不得声称 verified。"""

    ok: bool
    schema_version: str = SCHEMA_VERSION
    role: str
    status: Status
    task: str = ""
    evidence: list[EvidenceItem] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    handoff: Handoff | None = None
    error: str | None = None

    def require_verified_evidence(self) -> None:
        if self.status != "verified":
            return
        if not any(item.ok for item in self.evidence):
            raise ValueError(f"角色 {self.role} 不能在没有成功证据时标记 verified")
