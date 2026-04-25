"""C18 — best-effort time_cue → ISO date parser.

Pure function used by the C18 backfill helper (and any future caller
that needs to convert a free-text temporal hint into the structured
``event_date_iso`` shape stored on ``:Event`` nodes).

Output is a TRUNCATED ISO string:
  - ``"YYYY"``        — year-only ("1880")
  - ``"YYYY-MM"``     — year-month ("1880-06")
  - ``"YYYY-MM-DD"``  — full ISO date

This format is sort-stable lexicographically (for non-negative years
in 1000-2999) so range queries on ``event_date_iso`` work via plain
string comparison.

Returns ``None`` for unparseable input. The LLM event extractor remains
the gold standard — this parser is the cheap backfill path for
recovering structured dates from existing ``time_cue`` strings written
under the pre-C18 schema.

**Known limitations** (see ADR §6.10-11):
  - **BC/AD ambiguity**: ``parse_time_cue_to_iso("1880 BC")`` returns
    ``"1880"`` (bare-year regex doesn't see the "BC" suffix), silently
    converting BC to AD. Fictional fiction set in antiquity is rare;
    recoverable via LLM re-extraction or manual edit.
  - **Northern-hemisphere season bias**: spring → March, summer → June,
    autumn/fall → September, winter → December. Southern-hemisphere
    fiction would want the opposite — out of scope for v1.
  - **Year range [1000, 2999] only**: medieval ("year 999") and
    sci-fi ("year 30000") years skipped to avoid false-positives on
    chapter numbers, page counts, or character ages.

See ADR ``docs/03_planning/KNOWLEDGE_SERVICE_EVENT_WALL_CLOCK_DATE_ADR.md``
§5.4 for the pattern set + rationale.
"""

from __future__ import annotations

import re

__all__ = ["parse_time_cue_to_iso"]


# Pattern order matters — more specific patterns must run first so a
# bare-year regex doesn't strip the surrounding month/season context
# from a "Month Year" or "Season Year" string. ``re.search`` returns
# the first match by left-to-right scan, but the dispatch below tries
# patterns in priority order and returns on first hit.

_ISO_DATE_RE = re.compile(
    r"^\s*(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})\s*$",
)

_MONTHS = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)
_MONTH_TO_NUM = {name: f"{i + 1:02d}" for i, name in enumerate(_MONTHS)}

# "June 15, 1880" / "June 15 1880" / "15 June 1880" — handle both
# (Month Day Year) and (Day Month Year) orderings since fiction can use
# either.
_MONTH_DAY_YEAR_RE = re.compile(
    rf"\b(?P<month>{'|'.join(_MONTHS)})\s+(?P<day>\d{{1,2}}),?\s+(?P<year>\d{{4}})\b",
    re.IGNORECASE,
)
_DAY_MONTH_YEAR_RE = re.compile(
    rf"\b(?P<day>\d{{1,2}})\s+(?P<month>{'|'.join(_MONTHS)}),?\s+(?P<year>\d{{4}})\b",
    re.IGNORECASE,
)

_MONTH_YEAR_RE = re.compile(
    rf"\b(?P<month>{'|'.join(_MONTHS)})\s+(?P<year>\d{{4}})\b",
    re.IGNORECASE,
)

# Season → representative month (Northern Hemisphere — out-of-scope to
# negotiate per-fiction-setting; ADR §6 documents this bias).
_SEASONS = {
    "spring": "03",
    "summer": "06",
    "autumn": "09",
    "fall": "09",
    "winter": "12",
}
_SEASON_YEAR_RE = re.compile(
    rf"\b(?P<season>{'|'.join(_SEASONS)})\s+(?:of\s+)?(?P<year>\d{{4}})\b",
    re.IGNORECASE,
)

# Bare year — most ambiguous, runs last. Restricted to [1000, 2999]
# to avoid matching chapter numbers, page counts, or character ages
# embedded in narrative cues.
_BARE_YEAR_RE = re.compile(r"\b(?P<year>[12]\d{3})\b")


def _is_valid_iso_full(year: str, month: str, day: str) -> bool:
    """Cheap calendar validation. Catches month [01-12] + day [01-31]
    structurally; doesn't catch Feb 30 (would need calendar awareness).
    Acceptable for backfill — the parser is best-effort by design."""
    if not (1 <= int(month) <= 12):
        return False
    if not (1 <= int(day) <= 31):
        return False
    return True


def parse_time_cue_to_iso(text: str | None) -> str | None:
    """Parse a free-text temporal hint into a truncated ISO date.

    Returns ``None`` for unparseable input (the dominant case — most
    ``time_cue`` strings are vague phrases like "the next morning" or
    "in his youth" that don't carry a calendar date).

    Pattern priority (first match wins):
      1. Already-ISO ``YYYY-MM-DD`` (whole-string match)
      2. ``Month Day, Year`` or ``Month Day Year``
      3. ``Day Month Year`` (some fiction prefers this ordering)
      4. ``Month Year`` → ``YYYY-MM``
      5. ``Season Year`` → ``YYYY-MM`` (Northern Hemisphere season-to-month)
      6. Bare 4-digit year in [1000-2999] → ``YYYY``
    """
    if not text:
        return None

    # 1. Whole-string ISO.
    m = _ISO_DATE_RE.match(text)
    if m:
        y, mo, d = m.group("y"), m.group("m"), m.group("d")
        if _is_valid_iso_full(y, mo, d):
            return f"{y}-{mo}-{d}"
        return None

    # 2-3. Full date with named month (both orderings).
    for pat in (_MONTH_DAY_YEAR_RE, _DAY_MONTH_YEAR_RE):
        m = pat.search(text)
        if m:
            month_num = _MONTH_TO_NUM[m.group("month").lower()]
            day_str = f"{int(m.group('day')):02d}"
            year_str = m.group("year")
            if _is_valid_iso_full(year_str, month_num, day_str):
                return f"{year_str}-{month_num}-{day_str}"
            # Day out of [1-31] but month was valid — fall through to
            # month-year.
            return f"{year_str}-{month_num}"

    # 4. Month + year.
    m = _MONTH_YEAR_RE.search(text)
    if m:
        month_num = _MONTH_TO_NUM[m.group("month").lower()]
        return f"{m.group('year')}-{month_num}"

    # 5. Season + year.
    m = _SEASON_YEAR_RE.search(text)
    if m:
        return f"{m.group('year')}-{_SEASONS[m.group('season').lower()]}"

    # 6. Bare year.
    m = _BARE_YEAR_RE.search(text)
    if m:
        return m.group("year")

    return None
