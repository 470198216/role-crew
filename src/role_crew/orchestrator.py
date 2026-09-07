from __future__ import annotations

from pathlib import Path
from typing import Any

from role_crew.envelope import Envelope, EvidenceItem, Handoff
from role_crew.executor import Executor, ToolError
from role_crew.registry import RoleCard
from role_crew.trace import Tracer

DEMO_PATH = "hello.txt"
DEMO_TEXT = "OK"
DEMO_TASK = f"在 workspace 创建 {DEMO_PATH}，内容为 {DEMO_TEXT}，确认后再结束。"


def _evidence(tool: str, ok: bool, summary: str) -> EvidenceItem:
    return EvidenceItem(tool=tool, ok=ok, summary=summary)


def run_dispatcher(executor: Executor, role: RoleCard, task: str) -> Envelope:
    listed = executor.run(role, "list_roles")
    env = Envelope(
        ok=listed.ok,
        role=role.id,
        status="verified" if listed.ok else "failed",
        task=task,
        evidence=[_evidence("list_roles", listed.ok, listed.summary)],
        result=listed.data,
        handoff=Handoff(to="fixer", task=task) if listed.ok else None,
        error=listed.error,
    )
    env.require_verified_evidence()
    return env


def run_fixer(executor: Executor, role: RoleCard, task: str) -> Envelope:
    written = executor.run(role, "write_text", path=DEMO_PATH, text=DEMO_TEXT)
    if not written.ok:
        env = Envelope(
            ok=False,
            role=role.id,
            status="failed",
            task=task,
            evidence=[_evidence("write_text", False, written.summary)],
            result=written.data,
            error=written.error,
        )
        return env
    read = executor.run(role, "read_file", path=DEMO_PATH)
    confirmed = read.ok and read.data.get("text") == DEMO_TEXT
    env = Envelope(
        ok=confirmed,
        role=role.id,
        status="verified" if confirmed else "failed",
        task=task,
        evidence=[
            _evidence("write_text", True, written.summary),
            _evidence("read_file", read.ok, read.summary),
        ],
        result={"path": DEMO_PATH, "text": read.data.get("text")},
        handoff=Handoff(to="verifier", task=f"确认 {DEMO_PATH} 内容为 {DEMO_TEXT}") if confirmed else None,
        error=None if confirmed else "写后回读不一致",
    )
    env.require_verified_evidence()
    return env


def run_verifier(executor: Executor, role: RoleCard, task: str) -> Envelope:
    read = executor.run(role, "read_file", path=DEMO_PATH)
    text = (read.data or {}).get("text")
    passed = read.ok and text == DEMO_TEXT
    env = Envelope(
        ok=passed,
        role=role.id,
        status="verified" if passed else "failed",
        task=task,
        evidence=[_evidence("read_file", read.ok, read.summary)],
        result={"path": DEMO_PATH, "text": text, "expected": DEMO_TEXT},
        handoff=None if passed else Handoff(to="fixer", task=f"把 {DEMO_PATH} 改成 {DEMO_TEXT}"),
        error=None if passed else f"期望 {DEMO_TEXT!r}，实际 {text!r}",
    )
    if passed:
        env.require_verified_evidence()
    return env


def run_with_llm(task: str, crew: Any) -> list[Envelope]:
    """dispatcher 起手；模型可 call_role，也可 submit need_peer 由编排器接着跑。"""
    from role_crew.actor import Actor

    crew.tracer.log("run_start", task=task)
    env = Actor(crew.roles["dispatcher"], crew, depth=0).run(task)
    hops = 0
    while env.status == "need_peer" and env.handoff and hops < crew.settings.max_peer_depth:
        hops += 1
        nxt = crew.roles.get(env.handoff.to)
        if nxt is None:
            break
        env = Actor(nxt, crew, depth=hops).run(env.handoff.task)
    crew.tracer.log(
        "run_end",
        ok=bool(crew.envelopes) and crew.envelopes[-1].status == "verified",
    )
    return crew.envelopes


def run_demo(workspace: Path | None = None, tracer: Tracer | None = None) -> list[Envelope]:
    """无 LLM：dispatcher 点名 → fixer 写并回读 → verifier 再读。"""
    tracer = tracer or Tracer()
    executor = Executor(workspace=workspace, tracer=tracer)
    roles = executor.roles
    tracer.log("demo_start", task=DEMO_TASK)

    steps = [
        ("dispatcher", run_dispatcher),
        ("fixer", run_fixer),
        ("verifier", run_verifier),
    ]
    envelopes: list[Envelope] = []
    task = DEMO_TASK
    for role_id, fn in steps:
        role = roles[role_id]
        env = fn(executor, role, task)
        tracer.log("envelope", envelope=env.model_dump())
        envelopes.append(env)
        if env.status != "verified":
            break
        if env.handoff:
            task = env.handoff.task
    tracer.log("demo_end", ok=bool(envelopes) and envelopes[-1].status == "verified")
    return envelopes
