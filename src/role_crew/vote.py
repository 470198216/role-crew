from __future__ import annotations

import json
from collections import Counter
from typing import Any

from role_crew.envelope import Envelope


def collect_repos(envelopes: list[Envelope]) -> list[str]:
    found: set[str] = set()
    for env in envelopes:
        items = (env.result or {}).get("items")
        if not isinstance(items, list):
            continue
        for row in items:
            if isinstance(row, dict) and row.get("repo"):
                found.add(str(row["repo"]))
    return sorted(found)


def nucleus(envelopes: list[Envelope]) -> dict[str, Any]:
    """可比的核：不包含 note 等自由文本。"""
    last = envelopes[-1] if envelopes else None
    result = (last.result or {}) if last else {}
    return {
        "status": last.status if last else "failed",
        "repos": collect_repos(envelopes),
        "path": result.get("path"),
        "text": result.get("text"),
        "has_error": bool(last.error) if last else True,
    }


def nucleus_key(envelopes: list[Envelope]) -> str:
    return json.dumps(nucleus(envelopes), ensure_ascii=False, sort_keys=True, default=str)


def tally(
    trials: list[list[Envelope]],
    min_ratio: float = 0.5,
) -> dict[str, Any]:
    """对多次 run 的信封列表按核投票。"""
    keys: list[str] = []
    keyed: dict[str, list[int]] = {}
    for i, envelopes in enumerate(trials):
        if not envelopes:
            key = json.dumps({"status": "empty"}, sort_keys=True)
        else:
            key = nucleus_key(envelopes)
        keys.append(key)
        keyed.setdefault(key, []).append(i)
    counts = Counter(keys)
    n = len(trials)
    winner_key, k = counts.most_common(1)[0] if counts else ("", 0)
    probability = (k / n) if n else 0.0
    winner_idx = keyed.get(winner_key, [None])[0]
    winner_envs = trials[winner_idx] if winner_idx is not None else []
    clusters = []
    for key, idxs in sorted(keyed.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        last = trials[idxs[0]][-1] if trials[idxs[0]] else None
        clusters.append(
            {
                "count": len(idxs),
                "probability": round(len(idxs) / n, 4) if n else 0.0,
                "nucleus": json.loads(key),
                "sample_note": ((last.result or {}).get("note") if last else None),
                "trials": idxs,
            }
        )
    return {
        "n": n,
        "k": k,
        "probability": round(probability, 4),
        "unstable": probability < min_ratio,
        "winner_trial": winner_idx,
        "winner": winner_envs[-1].model_dump() if winner_envs else None,
        "winner_steps": [e.model_dump() for e in winner_envs],
        "clusters": clusters,
    }
