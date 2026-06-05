"""Fractional (LexoRank-lite) ordering keys for `outline_node.rank`.

A node's position among its siblings is a short base-36 string. To insert
between two siblings we compute a string strictly between their ranks — so a
reorder/insert touches ONE row, never a renumber of the whole list.

Alphabet = "0123456789abcdefghijklmnopqrstuvwxyz" (lowercase). ASCII order of
these chars is ascending ('0' < … < '9' < 'a' < … < 'z'), so plain string
comparison (and Postgres `ORDER BY rank`, default C-ish collation on ASCII)
matches numeric order. Ranks never contain a trailing '0' digit from this
algorithm, so they stay canonical and the space between any two is unbounded.
"""

from __future__ import annotations

_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"
_BASE = len(_DIGITS)  # 36
_INDEX = {c: i for i, c in enumerate(_DIGITS)}


def _digit(c: str) -> int:
    try:
        return _INDEX[c]
    except KeyError as exc:  # pragma: no cover - guards malformed stored ranks
        raise ValueError(f"invalid rank digit: {c!r}") from exc


def rank_between(lo: str | None, hi: str | None) -> str:
    """Return a rank `r` with ``lo < r < hi`` lexicographically.

    ``lo=None`` is the open lower bound (before everything); ``hi=None`` is the
    open upper bound (after everything). ``rank_between(None, None)`` yields the
    canonical first rank. Requires ``lo < hi`` when both are given.
    """
    if lo is not None and hi is not None and lo >= hi:
        raise ValueError(f"rank_between requires lo < hi, got {lo!r} >= {hi!r}")

    result: list[str] = []
    hi_open = hi is None
    i = 0
    while True:
        lo_d = _digit(lo[i]) if (lo is not None and i < len(lo)) else 0
        if hi_open:
            hi_d = _BASE
        elif i < len(hi):  # type: ignore[arg-type]
            hi_d = _digit(hi[i])
        else:
            # hi exhausted during a shared-prefix walk: only reachable if lo
            # extends hi (lo >= hi), excluded by the precondition above.
            hi_d = _BASE
            hi_open = True

        if lo_d == hi_d:
            result.append(_DIGITS[lo_d])
            i += 1
            continue

        gap = hi_d - lo_d
        if gap >= 2:
            result.append(_DIGITS[lo_d + gap // 2])
            return "".join(result)

        # Adjacent (gap == 1): no digit fits here. Take lo's digit and keep
        # descending — every further digit is > lo and still < hi, so hi is
        # now effectively open for the remainder.
        result.append(_DIGITS[lo_d])
        hi_open = True
        i += 1


def first_rank() -> str:
    """Canonical rank for the first node in an empty sibling list."""
    return rank_between(None, None)


def rank_after(last: str | None) -> str:
    """Append-to-end: a rank greater than ``last`` (or first if list empty)."""
    return rank_between(last, None)


def rank_before(first: str | None) -> str:
    """Prepend: a rank less than ``first`` (or first if list empty)."""
    return rank_between(None, first)
