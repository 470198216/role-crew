from __future__ import annotations

import json
import sys
from typing import Optional

import typer

from role_crew.actor import Actor
from role_crew.config import Settings
from role_crew.executor import Executor, ToolError
from role_crew.llm import LLMClient, LLMNotConfigured
from role_crew.orchestrator import run_demo
from role_crew.registry import load_registry
from role_crew.trace import Tracer

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

app = typer.Typer(add_completion=False, no_args_is_help=True, help="多角色：先执行，再用同一信封交接")


def _echo_json(obj: object) -> None:
    typer.echo(json.dumps(obj, ensure_ascii=False, indent=2))


@app.command("roles")
def roles_cmd() -> None:
    """列出角色卡。"""
    cards = load_registry()
    _echo_json([c.directory_row() for c in cards.values()])


@app.command("tool")
def tool_cmd(
    role: str = typer.Option(..., "--role", help="角色 id"),
    name: str = typer.Option(..., "--name", help="白名单工具名"),
    arg: Optional[list[str]] = typer.Option(None, "--arg", help="k=v，可重复"),
) -> None:
    """不调模型，直接跑某个角色的一个工具。"""
    cards = load_registry()
    if role not in cards:
        raise typer.BadParameter(f"未知角色 {role}")
    kwargs: dict[str, str] = {}
    for item in arg or []:
        if "=" not in item:
            raise typer.BadParameter(f"--arg 必须是 k=v: {item}")
        k, v = item.split("=", 1)
        kwargs[k] = v
    tracer = Tracer()
    executor = Executor(tracer=tracer, roles=cards)
    try:
        result = executor.run(cards[role], name, **kwargs)
    except ToolError as exc:
        _echo_json({"ok": False, "error": str(exc)})
        raise typer.Exit(1) from exc
    payload = result.as_payload()
    payload["trace"] = str(tracer.path)
    _echo_json(payload)
    if not result.ok:
        raise typer.Exit(1)


@app.command("demo")
def demo_cmd() -> None:
    """无 LLM 演示：dispatcher → fixer 写 hello.txt=OK → verifier 再读确认。"""
    tracer = Tracer()
    envelopes = run_demo(tracer=tracer)
    _echo_json(
        {
            "ok": envelopes[-1].status == "verified",
            "task": envelopes[0].task,
            "steps": [env.model_dump() for env in envelopes],
            "trace": str(tracer.path),
        }
    )
    if envelopes[-1].status != "verified":
        raise typer.Exit(1)


@app.command("run")
def run_cmd(
    task: str = typer.Option(..., "--task", help="用户目标（下一版由 LLM 拆给各角色）"),
) -> None:
    """预留：接 API Key 后的多角色循环。第一版会明确拒绝。"""
    settings = Settings()
    llm = LLMClient(settings)
    tracer = Tracer()
    cards = load_registry()
    executor = Executor(tracer=tracer, roles=cards)
    actor = Actor(cards["dispatcher"], executor, llm, tracer)
    try:
        actor.run(task)
    except LLMNotConfigured as exc:
        _echo_json(
            {
                "ok": False,
                "error": str(exc),
                "llm_ready": llm.ready(),
                "hint": "现在请用 role-crew demo；配好 .env 里的 LLM_API_KEY 后再实现 run",
            }
        )
        raise typer.Exit(2) from exc


def main() -> None:
    app()


if __name__ == "__main__":
    main()
