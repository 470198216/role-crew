from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from role_crew.config import ROLES_DIR, load_yaml


@dataclass(frozen=True)
class RoleCard:
    id: str
    summary: str
    tools: tuple[str, ...]
    can_call: tuple[str, ...]

    def directory_row(self) -> dict[str, object]:
        return {
            "id": self.id,
            "summary": self.summary,
            "tools": list(self.tools),
            "can_call": list(self.can_call),
        }


def load_role(path: Path) -> RoleCard:
    data = load_yaml(path)
    role_id = str(data["id"])
    return RoleCard(
        id=role_id,
        summary=str(data.get("summary") or role_id),
        tools=tuple(str(x) for x in (data.get("tools") or ())),
        can_call=tuple(str(x) for x in (data.get("can_call") or ())),
    )


def load_registry(roles_dir: Path | None = None) -> dict[str, RoleCard]:
    folder = roles_dir or ROLES_DIR
    cards = [load_role(p) for p in sorted(folder.glob("*.yaml"))]
    if not cards:
        raise FileNotFoundError(f"没有角色 YAML: {folder}")
    by_id = {c.id: c for c in cards}
    if len(by_id) != len(cards):
        raise ValueError("角色 id 重复")
    for card in cards:
        for peer in card.can_call:
            if peer not in by_id:
                raise ValueError(f"角色 {card.id} 的 can_call 指向未知角色 {peer}")
    return by_id
