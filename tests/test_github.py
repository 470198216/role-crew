from __future__ import annotations

from pathlib import Path

import pytest

from role_crew.executor import Executor, ToolError
from role_crew.github_tools import github_readme, github_search
from role_crew.registry import load_registry


def test_dispatcher_cannot_github(tmp_path: Path) -> None:
    cards = load_registry()
    ex = Executor(workspace=tmp_path, roles=cards)
    with pytest.raises(ToolError, match="不能使用工具"):
        ex.run(cards["dispatcher"], "github_search", q="skill")


def test_github_search_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(path, token, params=None):
        return (
            200,
            {
                "total_count": 1,
                "items": [
                    {
                        "full_name": "anthropics/skills",
                        "html_url": "https://github.com/anthropics/skills",
                        "stargazers_count": 10,
                        "description": "Agent Skills",
                        "topics": ["agents"],
                    }
                ],
            },
            "",
        )

    monkeypatch.setattr("role_crew.github_tools._get", fake_get)
    result = github_search("skill")
    assert result.ok
    assert result.data["items"][0]["repo"] == "anthropics/skills"


def test_github_readme_rejects_url() -> None:
    with pytest.raises(ToolError):
        github_readme("https://github.com/a/b")
