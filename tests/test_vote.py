from __future__ import annotations

from role_crew.envelope import Envelope, EvidenceItem
from role_crew.vote import nucleus_key, tally


def _env(status: str, repos: list[str] | None = None, note: str = "x", text: str | None = None) -> Envelope:
    items = [{"repo": r} for r in (repos or [])]
    evidence = [EvidenceItem(tool="github_search", ok=True, summary="ok")] if status == "verified" else []
    return Envelope(
        ok=status == "verified",
        role="dispatcher",
        status=status,  # type: ignore[arg-type]
        evidence=evidence,
        result={"items": items, "note": note, "text": text},
    )


def test_nucleus_ignores_note() -> None:
    a = [_env("verified", ["a/b"], note="说法一")]
    b = [_env("verified", ["a/b"], note="说法二")]
    assert nucleus_key(a) == nucleus_key(b)


def test_tally_majority() -> None:
    trials = [
        [_env("verified", ["owner/one"])],
        [_env("verified", ["owner/one"], note="另一个 note")],
        [_env("verified", ["owner/two"])],
    ]
    out = tally(trials, min_ratio=0.5)
    assert out["n"] == 3
    assert out["k"] == 2
    assert out["probability"] == 0.6667
    assert out["unstable"] is False
    assert out["winner"]["result"]["items"][0]["repo"] == "owner/one"
    assert len(out["clusters"]) == 2


def test_tally_unstable_when_split() -> None:
    trials = [
        [_env("verified", ["a/a"])],
        [_env("verified", ["b/b"])],
        [_env("failed", [])],
    ]
    out = tally(trials, min_ratio=0.5)
    assert out["k"] == 1
    assert out["unstable"] is True
