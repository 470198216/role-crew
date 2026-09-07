from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from role_crew.config import CONFIG_DIR, WORKSPACE_DIR, load_yaml
from role_crew.registry import RoleCard, load_registry
from role_crew.trace import Tracer


class ToolError(ValueError):
    """白名单或参数不合法。"""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args: tuple[str, ...]
    reserved: bool = False


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    data: dict[str, Any]
    error: str | None = None
    summary: str = ""

    def as_payload(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": self.ok, "data": self.data, "summary": self.summary}
        if self.error:
            out["error"] = self.error
        return out


def load_tool_specs() -> tuple[dict[str, ToolSpec], int, int]:
    cfg = load_yaml(CONFIG_DIR / "tools.yaml")
    defaults = cfg.get("defaults") or {}
    specs: dict[str, ToolSpec] = {}
    for name, raw in (cfg.get("tools") or {}).items():
        specs[name] = ToolSpec(
            name=name,
            description=str(raw.get("description") or name),
            args=tuple(str(x) for x in (raw.get("args") or ())),
            reserved=bool(raw.get("reserved")),
        )
    return (
        specs,
        int(defaults.get("max_output_bytes", 65536)),
        int(defaults.get("max_text_chars", 4096)),
    )


def resolve_workspace_path(rel: str, workspace: Path) -> Path:
    if not rel or rel.strip() != rel:
        raise ToolError("路径不能为空或带首尾空白")
    raw = Path(rel)
    if raw.is_absolute() or raw.drive:
        raise ToolError("只允许 workspace 相对路径")
    if any(part in ("..", "") for part in raw.parts):
        raise ToolError("路径不能包含 ..")
    if raw.suffix.lower() != ".txt":
        raise ToolError("第一版只允许 .txt")
    workspace = workspace.resolve()
    target = (workspace / raw).resolve()
    try:
        target.relative_to(workspace)
    except ValueError as exc:
        raise ToolError("路径逃出 workspace") from exc
    return target


class Executor:
    def __init__(
        self,
        workspace: Path | None = None,
        tracer: Tracer | None = None,
        roles: dict[str, RoleCard] | None = None,
    ) -> None:
        self.workspace = (workspace or WORKSPACE_DIR).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.tracer = tracer
        self.roles = roles if roles is not None else load_registry()
        self.specs, self.max_output_bytes, self.max_text_chars = load_tool_specs()

    def run(self, role_card: RoleCard, name: str, **args: Any) -> ToolResult:
        if name not in role_card.tools:
            raise ToolError(f"角色 {role_card.id} 不能使用工具 {name}")
        spec = self.specs.get(name)
        if spec is None:
            raise ToolError(f"未知工具 {name}")
        if spec.reserved:
            result = ToolResult(ok=False, data={}, error=f"{name} 预留到下一版（接 LLM 后启用）", summary="reserved")
            self._log(role_card.id, name, args, result)
            return result
        missing = [key for key in spec.args if key not in args or args[key] is None]
        if missing:
            raise ToolError(f"工具 {name} 缺少参数: {', '.join(missing)}")
        extra = [key for key in args if key not in spec.args]
        if extra:
            raise ToolError(f"工具 {name} 多余参数: {', '.join(extra)}")

        handlers = {
            "list_roles": self._list_roles,
            "list_workspace": self._list_workspace,
            "write_text": self._write_text,
            "read_file": self._read_file,
        }
        handler = handlers.get(name)
        if handler is None:
            raise ToolError(f"工具 {name} 未实现")
        result = handler(**args)
        self._log(role_card.id, name, args, result)
        return result

    def _log(self, role_id: str, name: str, args: dict[str, Any], result: ToolResult) -> None:
        if self.tracer is None:
            return
        safe_args = {k: (v if k != "text" else f"<{len(str(v))} chars>") for k, v in args.items()}
        self.tracer.log("tool", role=role_id, tool=name, args=safe_args, result=result.as_payload())

    def _clip(self, text: str) -> str:
        raw = text.encode("utf-8")
        if len(raw) <= self.max_output_bytes:
            return text
        return raw[: self.max_output_bytes].decode("utf-8", errors="ignore") + "\n…(truncated)"

    def _list_roles(self) -> ToolResult:
        rows = [card.directory_row() for card in self.roles.values()]
        return ToolResult(ok=True, data={"roles": rows}, summary=f"{len(rows)} 个角色")

    def _list_workspace(self) -> ToolResult:
        files = sorted(
            str(p.relative_to(self.workspace)).replace("\\", "/")
            for p in self.workspace.rglob("*")
            if p.is_file() and p.name != ".gitkeep"
        )
        return ToolResult(ok=True, data={"files": files}, summary=f"{len(files)} 个文件")

    def _write_text(self, path: str, text: str) -> ToolResult:
        if not isinstance(text, str):
            raise ToolError("text 必须是字符串")
        if len(text) > self.max_text_chars:
            raise ToolError(f"text 超过 {self.max_text_chars} 字符")
        target = resolve_workspace_path(path, self.workspace)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return ToolResult(ok=True, data={"path": path, "bytes": target.stat().st_size}, summary=f"已写入 {path}")

    def _read_file(self, path: str) -> ToolResult:
        target = resolve_workspace_path(path, self.workspace)
        if not target.is_file():
            return ToolResult(ok=False, data={"path": path}, error="文件不存在", summary=f"没有 {path}")
        text = self._clip(target.read_text(encoding="utf-8"))
        return ToolResult(ok=True, data={"path": path, "text": text}, summary=f"读到 {path}（{len(text)} 字）")
