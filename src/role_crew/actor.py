from __future__ import annotations

from typing import Any

from role_crew.envelope import Envelope
from role_crew.executor import Executor
from role_crew.llm import LLMClient, LLMNotConfigured
from role_crew.registry import RoleCard
from role_crew.trace import Tracer

# 下一版：每轮把角色卡 + 同伴目录塞进 system，强制「无工具回执不得 verified」。
ROLE_SYSTEM_TEMPLATE = """你是角色 {role_id}。
职责：{summary}
你只能使用这些工具：{tools}
需要支援时可调用：{can_call}

规则：
1. 先执行，再下结论。禁止虚构 stdout。
2. 没有成功 evidence 不得 status=verified。
3. 自己的小目标验证后再交接。
4. 输出必须符合统一信封 JSON。

同伴目录：
{directory}
"""


class Actor:
    """单角色 think-act 循环。第一版不调 LLM，只提供提示词和将来的入口。"""

    def __init__(self, role: RoleCard, executor: Executor, llm: LLMClient, tracer: Tracer) -> None:
        self.role = role
        self.executor = executor
        self.llm = llm
        self.tracer = tracer

    def system_prompt(self, directory: list[dict[str, Any]]) -> str:
        return ROLE_SYSTEM_TEMPLATE.format(
            role_id=self.role.id,
            summary=self.role.summary,
            tools=", ".join(self.role.tools) or "(无)",
            can_call=", ".join(self.role.can_call) or "(无)",
            directory=directory,
        )

    def run(self, task: str) -> Envelope:
        self.tracer.log("actor_blocked", role=self.role.id, task=task)
        raise LLMNotConfigured("单角色循环依赖 LLM，第一版请用 `role-crew demo`")
