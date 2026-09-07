from __future__ import annotations

from pathlib import Path

import pytest

from role_crew.envelope import Envelope
from role_crew.executor import Executor, ToolError, resolve_workspace_path
from role_crew.orchestrator import DEMO_TEXT, run_demo, run_verifier
from role_crew.registry import load_registry
from role_crew.trace import Tracer


def test_verified_needs_evidence() -> None:
    env = Envelope(ok=True, role="fixer", status="verified", task="x")
    with pytest.raises(ValueError, match="没有成功证据"):
        env.require_verified_evidence()


def test_path_stays_in_workspace(tmp_path: Path) -> None:
    with pytest.raises(ToolError):
        resolve_workspace_path("../secret.txt", tmp_path)
    with pytest.raises(ToolError):
        resolve_workspace_path("C:/Windows/hi.txt", tmp_path)
    with pytest.raises(ToolError):
        resolve_workspace_path("note.md", tmp_path)
    got = resolve_workspace_path("hello.txt", tmp_path)
    assert got.parent == tmp_path.resolve()


def test_role_cannot_use_foreign_tool(tmp_path: Path) -> None:
    cards = load_registry()
    ex = Executor(workspace=tmp_path, roles=cards)
    with pytest.raises(ToolError, match="不能使用工具"):
        ex.run(cards["dispatcher"], "write_text", path="hello.txt", text="OK")


def test_call_role_reserved(tmp_path: Path) -> None:
    from role_crew.registry import RoleCard

    fake = RoleCard(id="dispatcher", summary="x", tools=("call_role",), can_call=("fixer",))
    ex = Executor(workspace=tmp_path)
    result = ex.run(fake, "call_role", role="fixer", task="x")
    assert result.ok is False
    assert "只能在 role-crew run" in (result.error or "")


def test_demo_pipeline(tmp_path: Path) -> None:
    tracer = Tracer()
    steps = run_demo(workspace=tmp_path, tracer=tracer)
    assert [s.role for s in steps] == ["dispatcher", "fixer", "verifier"]
    assert all(s.status == "verified" for s in steps)
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == DEMO_TEXT
    assert steps[-1].evidence and steps[-1].evidence[0].ok


def test_verifier_rejects_wrong_content(tmp_path: Path) -> None:
    cards = load_registry()
    ex = Executor(workspace=tmp_path, roles=cards)
    (tmp_path / "hello.txt").write_text("NO", encoding="utf-8")
    env = run_verifier(ex, cards["verifier"], "check")
    assert env.status == "failed"
    assert env.handoff and env.handoff.to == "fixer"
