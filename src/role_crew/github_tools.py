from __future__ import annotations

import base64
import re
from typing import Any
from urllib.parse import urlencode

import httpx

from role_crew.executor import ToolError, ToolResult

API = "https://api.github.com"
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
QUERY_MAX = 200


def _headers(token: str) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "role-crew-scout",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get(path: str, token: str, params: dict[str, Any] | None = None) -> tuple[int, Any, str]:
    url = API + path
    if params:
        url += "?" + urlencode(params)
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, headers=_headers(token))
    except httpx.ConnectError as exc:
        return 0, None, f"连不上 GitHub API: {exc}"
    try:
        body: Any = resp.json()
    except Exception:
        body = {"raw": resp.text[:500]}
    return resp.status_code, body, resp.text[:200]


def github_search(q: str, token: str = "") -> ToolResult:
    query = (q or "").strip()
    if not query:
        raise ToolError("q 不能为空")
    if len(query) > QUERY_MAX:
        raise ToolError(f"q 超过 {QUERY_MAX} 字符")
    status, body, raw = _get(
        "/search/repositories",
        token,
        {"q": query, "sort": "stars", "order": "desc", "per_page": "8"},
    )
    if status == 403:
        return ToolResult(
            ok=False,
            data={},
            error="GitHub API 限流。可在 .env 加 GITHUB_TOKEN（经典 PAT，public_repo 即可）",
            summary="限流",
        )
    if status != 200 or not isinstance(body, dict):
        return ToolResult(ok=False, data={"status": status, "body": body}, error=raw or f"HTTP {status}", summary="搜索失败")
    items = []
    for row in body.get("items") or []:
        items.append(
            {
                "repo": row.get("full_name"),
                "url": row.get("html_url"),
                "stars": row.get("stargazers_count"),
                "description": (row.get("description") or "")[:240],
                "topics": (row.get("topics") or [])[:8],
            }
        )
    return ToolResult(
        ok=True,
        data={"query": query, "total": body.get("total_count"), "items": items},
        summary=f"搜到 {len(items)} 个仓库（total={body.get('total_count')}）",
    )


def github_readme(repo: str, token: str = "") -> ToolResult:
    name = (repo or "").strip().lstrip("/")
    if not REPO_RE.match(name):
        raise ToolError("repo 必须是 owner/name，例如 anthropics/skills")
    status, body, raw = _get(f"/repos/{name}/readme", token)
    if status == 404:
        return ToolResult(ok=False, data={"repo": name}, error="没有 README", summary="无 README")
    if status != 200 or not isinstance(body, dict):
        return ToolResult(ok=False, data={"status": status, "repo": name}, error=raw or f"HTTP {status}", summary="读取失败")
    encoded = body.get("content") or ""
    try:
        text = base64.b64decode(encoded).decode("utf-8", errors="replace")
    except Exception:
        text = ""
    if len(text) > 6000:
        text = text[:6000] + "\n…(truncated)"
    return ToolResult(
        ok=True,
        data={"repo": name, "url": body.get("html_url"), "text": text},
        summary=f"读到 {name} README（{len(text)} 字）",
    )
