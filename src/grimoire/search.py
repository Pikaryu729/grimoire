"""Fuzzy search over commands.

Scoring is deliberately simple and deterministic: exact match beats prefix,
prefix beats substring, substring beats subsequence (fuzzy), and within each
band earlier/shorter matches win. Search runs across the command name, the
command text, the description, and tags; a command's best field score counts.
"""

from __future__ import annotations

from .store import Entry

_EXACT = 1000
_PREFIX = 900
_SUBSTRING = 600
_SUBSEQ = 300


def score(query: str, text: str) -> int | None:
    """Score ``query`` against ``text``; ``None`` means no match."""
    q = query.lower()
    t = text.lower()
    if not q:
        return None
    if q == t:
        return _EXACT
    if t.startswith(q):
        return _PREFIX - (len(t) - len(q))
    pos = t.find(q)
    if pos != -1:
        return _SUBSTRING - pos
    # Subsequence match: every query char appears in order, with a penalty
    # for gaps.
    search_from = 0
    gaps = 0
    for ch in q:
        idx = t.find(ch, search_from)
        if idx == -1:
            return None
        gaps += idx - search_from
        search_from = idx + 1
    return _SUBSEQ - gaps


def search(entries: list[Entry], query: str, limit: int | None = None) -> list[Entry]:
    """Return entries matching ``query``, best first."""
    ranked: list[tuple[int, Entry]] = []
    for entry in entries:
        best: int | None = None
        for text in (entry.name, entry.command, entry.description, *entry.tags):
            s = score(query, text)
            if s is not None and (best is None or s > best):
                best = s
        if best is not None:
            ranked.append((best, entry))
    ranked.sort(key=lambda pair: (-pair[0], pair[1].tome, pair[1].name))
    result = [entry for _, entry in ranked]
    if limit is not None:
        result = result[:limit]
    return result
