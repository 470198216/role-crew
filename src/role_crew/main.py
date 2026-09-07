from __future__ import annotations

import json
import sys
from typing import Optional

import typer

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
    task: str = typer.Option(..., "--task", help="用户目标，由 dispatcher 分给各角色执行"),
) -> None:
    """接 LLM：提问 → 工具 → 回执 → 再问，直到 verified 或步数用尽。"""
    from role_crew.actor import Crew
    from role_crew.orchestrator import run_with_llm

    settings = Settings()
    llm = LLMClient(settings)
    tracer = Tracer()
    cards = load_registry()
    executor = Executor(tracer=tracer, roles=cards)
    crew = Crew(settings=settings, llm=llm, executor=executor, tracer=tracer, roles=cards)
    try:
        envelopes = run_with_llm(task, crew)
    except LLMNotConfigured as exc:
        _echo_json({"ok": False, "error": str(exc), "llm_ready": llm.ready()})
        raise typer.Exit(2) from exc
    except Exception as exc:
        _echo_json({"ok": False, "error": str(exc), "trace": str(tracer.path)})
        raise typer.Exit(1) from exc
    last = envelopes[-1] if envelopes else None
    _echo_json(
        {
            "ok": bool(last and last.status == "verified"),
            "task": task,
            "model": settings.llm_model,
            "steps": [env.model_dump() for env in envelopes],
            "trace": str(tracer.path),
        }
    )
    if not last or last.status != "verified":
        raise typer.Exit(1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
