from __future__ import annotations

from role_crew.executor import ToolSpec
from role_crew.registry import RoleCard

SUBMIT_NAME = "submit_envelope"

SUBMIT_SPEC = {
    "type": "function",
    "function": {
        "name": SUBMIT_NAME,
        "description": (
            "结束本角色本轮工作并提交统一信封。"
            "必须先调用真正的操作工具拿到回执，再 submit。"
            "verified 表示自己的小目标已用工具验证。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["verified", "failed", "need_peer"],
                },
                "note": {"type": "string", "description": "给下一角色或用户的简短说明"},
                "handoff_to": {"type": "string", "description": "need_peer 时必填，必须是 can_call 里的角色"},
                "handoff_task": {"type": "string", "description": "交给对方的子任务"},
                "error": {"type": "string"},
            },
            "required": ["status"],
        },
    },
}


def openai_tools_for_role(role: RoleCard, specs: dict[str, ToolSpec]) -> list[dict]:
    out: list[dict] = []
    for name in role.tools:
        spec = specs.get(name)
        if spec is None:
            continue
        props = {arg: {"type": "string"} for arg in spec.args}
        required = list(spec.args)
        out.append(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": {
                        "type": "object",
                        "properties": props,
                        "required": required,
                    },
                },
            }
        )
    out.append(SUBMIT_SPEC)
    return out
