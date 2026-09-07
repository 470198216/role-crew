from __future__ import annotations

import json
from pathlib import Path

from role_crew.actor import Actor, Crew
from role_crew.config import Settings
from role_crew.executor import Executor
from role_crew.orchestrator import run_with_llm
from role_crew.registry import load_registry
from role_crew.trace import Tracer


def _call(name: str, args: dict, call_id: str) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
            }
        ],
    }


class FakeLLM:
    def __init__(self, script: list[dict]) -> None:
        self.script = list(script)

    def ready(self) -> bool:
        return True

    def ready_or_raise(self) -> None:
        return None

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        if not self.script:
            raise RuntimeError("FakeLLM script exhausted")
        return self.script.pop(0)


def test_llm_loop_writes_and_verifies(tmp_path: Path) -> None:
    script = [
        _call("list_roles", {}, "c1"),
        _call("call_role", {"role": "fixer", "task": "写 hello.txt 为 OK 并确认"}, "c2"),
        _call("write_text", {"path": "hello.txt", "text": "OK"}, "c3"),
        _call("read_file", {"path": "hello.txt"}, "c4"),
        _call("submit_envelope", {"status": "verified", "note": "已写并回读"}, "c5"),
        _call("submit_envelope", {"status": "verified", "note": "fixer 已完成"}, "c6"),
    ]
    llm = FakeLLM(script)
    cards = load_registry()
    tracer = Tracer()
    executor = Executor(workspace=tmp_path, tracer=tracer, roles=cards)
    crew = Crew(settings=Settings(), llm=llm, executor=executor, tracer=tracer, roles=cards)
    steps = run_with_llm("创建 hello.txt 内容 OK", crew)
    roles = [s.role for s in steps]
    assert "fixer" in roles and "dispatcher" in roles
    assert steps[-1].status == "verified"
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "OK"
    assert not llm.script
