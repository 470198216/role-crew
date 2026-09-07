from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from role_crew.config import Settings
from role_crew.envelope import Envelope, EvidenceItem, Handoff
from role_crew.executor import Executor, ToolError, ToolResult
from role_crew.llm import LLMClient
from role_crew.registry import RoleCard
from role_crew.tools_openai import SUBMIT_NAME, openai_tools_for_role
from role_crew.trace import Tracer

ROLE_SYSTEM_TEMPLATE = """你是角色 {role_id}。
职责：{summary}
你只能调用列出的 function。禁止虚构文件内容和命令输出。

规则：
1. 先调用操作工具，根据回执再下结论。
2. 没有成功工具回执，不得 submit status=verified。
3. 自己的小目标验证完，才能 call_role 或 need_peer 交接。
4. 结束本角色时必须调用 submit_envelope。
5. call_role 的 role 只能是：{can_call}

同伴目录：
{directory}
"""


@dataclass
class Crew:
    settings: Settings
    llm: LLMClient
    executor: Executor
    tracer: Tracer
    roles: dict[str, RoleCard]
    envelopes: list[Envelope] = field(default_factory=list)
    stack: list[str] = field(default_factory=list)


def _parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _assistant_for_history(msg: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"role": "assistant"}
    if msg.get("content") is not None:
        out["content"] = msg.get("content")
    if msg.get("tool_calls"):
        out["tool_calls"] = msg["tool_calls"]
    if msg.get("reasoning_content"):
        out["reasoning_content"] = msg["reasoning_content"]
    return out


class Actor:
    def __init__(self, role: RoleCard, crew: Crew, depth: int = 0) -> None:
        self.role = role
        self.crew = crew
        self.depth = depth

    def system_prompt(self) -> str:
        directory = [c.directory_row() for c in self.crew.roles.values()]
        return ROLE_SYSTEM_TEMPLATE.format(
            role_id=self.role.id,
            summary=self.role.summary,
            can_call=", ".join(self.role.can_call) or "(无)",
            directory=json.dumps(directory, ensure_ascii=False),
        )

    def run(self, task: str) -> Envelope:
        if self.role.id in self.crew.stack:
            return Envelope(
                ok=False,
                role=self.role.id,
                status="failed",
                task=task,
                error=f"角色循环调用：{' → '.join(self.crew.stack + [self.role.id])}",
            )
        self.crew.stack.append(self.role.id)
        try:
            return self._run_loop(task)
        finally:
            self.crew.stack.pop()

    def _run_loop(self, task: str) -> Envelope:
        evidence: list[EvidenceItem] = []
        last_data: dict[str, Any] = {}
        tools = openai_tools_for_role(self.role, self.crew.executor.specs)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt()},
            {"role": "user", "content": f"任务：{task}\n先执行工具，再 submit_envelope。"},
        ]
        self.crew.tracer.log("actor_start", role=self.role.id, task=task, depth=self.depth)

        for step in range(self.crew.settings.max_agent_steps):
            msg = self.crew.llm.chat(messages, tools=tools)
            self.crew.tracer.log("llm_message", role=self.role.id, step=step, has_tools=bool(msg.get("tool_calls")))
            calls = msg.get("tool_calls") or []
            if calls:
                messages.append(_assistant_for_history(msg))
                for call in calls:
                    fn = call.get("function") or {}
                    name = str(fn.get("name") or "")
                    args = _parse_args(fn.get("arguments"))
                    result = self._exec(name, args, task, evidence, last_data)
                    if name == SUBMIT_NAME and isinstance(result.data.get("envelope"), dict):
                        env = Envelope.model_validate(result.data["envelope"])
                        self.crew.envelopes.append(env)
                        self.crew.tracer.log("envelope", envelope=env.model_dump())
                        return env
                    payload = result.as_payload()
                    if name != SUBMIT_NAME and name != "call_role":
                        last_data = result.data or last_data
                    messages.append(
                        {
                            "role": "tool",
                            "name": name,
                            "tool_call_id": call.get("id") or f"call_{step}_{name}",
                            "content": json.dumps(payload, ensure_ascii=False),
                        }
                    )
                continue

            content = (msg.get("content") or "").strip()
            messages.append(_assistant_for_history(msg) if msg.get("content") is not None else {"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": "不要只说话。请调用工具，完成后调用 submit_envelope。",
                }
            )

        env = Envelope(
            ok=False,
            role=self.role.id,
            status="failed",
            task=task,
            evidence=evidence,
            result=last_data,
            error=f"超过 MAX_AGENT_STEPS={self.crew.settings.max_agent_steps}",
        )
        self.crew.envelopes.append(env)
        return env

    def _exec(
        self,
        name: str,
        args: dict[str, Any],
        task: str,
        evidence: list[EvidenceItem],
        last_data: dict[str, Any],
    ) -> ToolResult:
        if name == SUBMIT_NAME:
            return self._submit(args, task, evidence, last_data)
        if name == "call_role":
            return self._call_role(args, evidence)
        try:
            result = self.crew.executor.run(self.role, name, **args)
        except ToolError as exc:
            result = ToolResult(ok=False, data={}, error=str(exc), summary=str(exc))
        evidence.append(EvidenceItem(tool=name, ok=result.ok, summary=result.summary or result.error or name))
        return result

    def _call_role(self, args: dict[str, Any], evidence: list[EvidenceItem]) -> ToolResult:
        peer_id = str(args.get("role") or "")
        subtask = str(args.get("task") or "")
        if peer_id not in self.role.can_call:
            result = ToolResult(ok=False, data={}, error=f"不能调用 {peer_id}", summary="call_role 拒绝")
            evidence.append(EvidenceItem(tool="call_role", ok=False, summary=result.summary))
            return result
        if self.depth >= self.crew.settings.max_peer_depth:
            result = ToolResult(ok=False, data={}, error="超过 MAX_PEER_DEPTH", summary="深度用尽")
            evidence.append(EvidenceItem(tool="call_role", ok=False, summary=result.summary))
            return result
        if not any(item.ok for item in evidence):
            result = ToolResult(
                ok=False,
                data={},
                error="先完成本角色的操作并拿到成功回执，再 call_role",
                summary="未自检",
            )
            evidence.append(EvidenceItem(tool="call_role", ok=False, summary=result.summary))
            return result
        peer = self.crew.roles.get(peer_id)
        if peer is None:
            result = ToolResult(ok=False, data={}, error=f"未知角色 {peer_id}", summary="未知角色")
            evidence.append(EvidenceItem(tool="call_role", ok=False, summary=result.summary))
            return result
        child = Actor(peer, self.crew, depth=self.depth + 1)
        env = child.run(subtask)
        ok = env.status == "verified"
        result = ToolResult(
            ok=ok,
            data={"envelope": env.model_dump()},
            error=env.error,
            summary=f"{peer_id} → {env.status}",
        )
        evidence.append(EvidenceItem(tool="call_role", ok=ok, summary=result.summary))
        return result

    def _submit(
        self,
        args: dict[str, Any],
        task: str,
        evidence: list[EvidenceItem],
        last_data: dict[str, Any],
    ) -> ToolResult:
        status = str(args.get("status") or "failed")
        if status not in {"verified", "failed", "need_peer"}:
            status = "failed"
        if status == "verified" and not any(item.ok for item in evidence):
            return ToolResult(
                ok=False,
                data={},
                error="没有成功 evidence，不能 verified。请先调用操作工具。",
                summary="submit 被拒",
            )
        handoff = None
        if status == "need_peer":
            to = str(args.get("handoff_to") or "")
            if to not in self.role.can_call:
                return ToolResult(
                    ok=False,
                    data={},
                    error=f"handoff_to 必须是 {list(self.role.can_call)}",
                    summary="submit 被拒",
                )
            handoff = Handoff(to=to, task=str(args.get("handoff_task") or task))
        note = str(args.get("note") or "")
        env = Envelope(
            ok=status == "verified",
            role=self.role.id,
            status=status,  # type: ignore[arg-type]
            task=task,
            evidence=list(evidence),
            result={**last_data, "note": note} if note else dict(last_data),
            handoff=handoff,
            error=str(args.get("error") or "") or None,
        )
        if status == "verified":
            env.require_verified_evidence()
        return ToolResult(ok=True, data={"envelope": env.model_dump()}, summary=f"submit {status}")
