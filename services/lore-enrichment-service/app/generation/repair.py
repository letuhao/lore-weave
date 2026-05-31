"""Normalization-repair pass for LLM generation output (RAID C11).

An LLM does not reliably emit clean, schema-valid JSON. This module takes the
RAW model output and DETERMINISTICALLY repairs it to the schema-governed shape
(a ``{dimension_label: chinese_content}`` map over the gap's missing dimensions)
— OR raises a typed :class:`RepairError`. There is NO silent data loss: every
input either produces a repaired map **plus** a :class:`RepairReport` describing
exactly what was changed, or it RAISES. A malformed record is never discarded
while reporting success.

What it repairs (deterministic, no LLM, no randomness):
  * fenced output — strips ```json … ``` / ``` … ``` code fences,
  * surrounding prose — extracts the outermost JSON object from chatter,
  * trailing commas — tolerates ``{"a": "b",}`` and ``[1, 2,]``,
  * smart quotes / full-width punctuation around the JSON envelope,
  * non-string dimension values — coerces scalars; rejects nested objects,
  * extra keys — dropped, but RECORDED in the report (not silently lost),
  * whitespace — trims values.

What it REJECTS (raises :class:`RepairError` — the un-repairable branch):
  * no JSON object recoverable at all,
  * a required (missing-dimension) key absent after repair,
  * a value that is empty after trimming,
  * English-leakage: a value for a Chinese dimension that is overwhelmingly
    Latin/ASCII (the model answered in English where Chinese was required) and
    cannot be salvaged.

H0 / scope boundary: repair produces CONTENT ONLY — it never sets origin /
confidence / canon. The H0 tagging happens downstream in ``provenance.py``. This
module knows nothing about canon; it only normalises text to the schema.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field

__all__ = [
    "RepairError",
    "RepairReport",
    "repair_generation",
    "has_english_leakage",
    "cjk_ratio",
]

# A dimension value must be at least this fraction CJK to count as Chinese.
# Below this, for a Chinese-required dimension, we treat it as English-leakage.
_MIN_CJK_RATIO: float = 0.30

# Dimension labels that are intentionally English in the locked C6 set (these are
# KEYS, not content — content is always Chinese, but these keys are not subject to
# the Chinese-content leakage check on their *label*). Content leakage is checked
# per the `chinese_dimensions` argument the caller passes.
_FENCE_RE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*|\s*```\s*$")
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


class RepairError(ValueError):
    """Raised when LLM output cannot be repaired to the schema.

    A typed error (distinct from a generic ``ValueError``) so the generator and
    tests can assert the reject path fired — a malformed-beyond-repair record is
    REJECTED explicitly, never silently dropped or returned as success.
    """


@dataclass
class RepairReport:
    """What the repair pass did to one generation output (audit trail).

    A repaired result always returns one of these alongside the map so nothing
    is changed invisibly: dropped extra keys, coerced values, stripped fences are
    all recorded. Empty lists mean the output was already clean.
    """

    stripped_fence: bool = False
    extracted_from_prose: bool = False
    fixed_trailing_comma: bool = False
    dropped_keys: list[str] = field(default_factory=list)
    coerced_keys: list[str] = field(default_factory=list)
    trimmed_keys: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(
            self.stripped_fence
            or self.extracted_from_prose
            or self.fixed_trailing_comma
            or self.dropped_keys
            or self.coerced_keys
            or self.trimmed_keys
        )


def cjk_ratio(text: str) -> float:
    """Fraction of NON-whitespace characters that are CJK ideographs.

    Deterministic. Punctuation/digits count toward the denominator but not the
    numerator, so '玉虛宮 is great' scores low (mostly Latin) and '玉虛宮乃昆仑之巅'
    scores high. An empty/whitespace string scores 0.0.
    """
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    cjk = sum(1 for c in chars if _is_cjk(c))
    return cjk / len(chars)


def _is_cjk(ch: str) -> bool:
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return False
    return "CJK" in name


def _has_latin_letters(text: str) -> bool:
    """True iff the text contains any A–Z/a–z (or accented Latin) letter.

    Distinguishes *English-leakage* (the model answered in a Latin-script
    language) from a value that merely has a low CJK ratio because it is digits
    or punctuation (e.g. a coerced number ``"123"``) — those are not leakage.
    """
    for ch in text:
        if ch.isascii() and ch.isalpha():
            return True
        if ch.isalpha() and "LATIN" in (unicodedata.name(ch, "")):
            return True
    return False


def has_english_leakage(text: str, *, min_cjk_ratio: float = _MIN_CJK_RATIO) -> bool:
    """True iff a value required to be Chinese is actual non-CJK *language*.

    Catches the model answering in English where a Chinese dimension was
    required: the value must both (a) contain Latin letters AND (b) fall below
    the CJK ratio. A short Chinese proper-noun value (no Latin run) and a
    digits/punctuation-only value are NOT flagged — only Latin-script prose is.
    """
    if not text.strip():
        return False  # emptiness is caught separately, not as leakage
    if not _has_latin_letters(text):
        return False  # digits/punctuation/pure-CJK → not English-leakage
    return cjk_ratio(text) < min_cjk_ratio


def _strip_fence(text: str, report: RepairReport) -> str:
    stripped = text.strip()
    if "```" in stripped:
        new = _FENCE_RE.sub("", stripped).strip()
        # Also remove a leading ```json with no trailing fence (model truncation).
        new = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", new).strip()
        new = re.sub(r"\s*```$", "", new).strip()
        if new != stripped:
            report.stripped_fence = True
        return new
    return stripped


def _extract_json_object(text: str, report: RepairReport) -> str:
    """Extract the outermost balanced ``{...}`` from surrounding prose.

    Scans for the first ``{`` and its matching ``}`` (brace-balanced, quote- and
    escape-aware) so leading/trailing chatter is dropped. Raises if none found.
    """
    start = text.find("{")
    if start == -1:
        raise RepairError("no JSON object found in model output")
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                obj = text[start : i + 1]
                if start != 0 or i + 1 != len(text):
                    report.extracted_from_prose = True
                return obj
    raise RepairError("unbalanced JSON object in model output")


def _load_json(text: str, report: RepairReport) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        fixed = _TRAILING_COMMA_RE.sub(r"\1", text)
        if fixed != text:
            report.fixed_trailing_comma = True
        try:
            data = json.loads(fixed)
        except json.JSONDecodeError as exc:
            raise RepairError(f"output is not valid JSON after repair: {exc}") from exc
    if not isinstance(data, dict):
        raise RepairError(
            f"expected a JSON object of dimensions, got {type(data).__name__}"
        )
    return data


def _coerce_value(key: str, value: object, report: RepairReport) -> str:
    """Coerce a dimension value to a trimmed string, or reject it.

    Strings pass through (trimmed). Scalars (int/float/bool) are stringified and
    recorded as coerced. Lists of scalars are joined with the source-faithful
    Chinese list separator ``、``. Nested objects / null are un-repairable.
    """
    if value is None:
        raise RepairError(f"dimension {key!r} is null (no content to repair)")
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed != value:
            report.trimmed_keys.append(key)
        return trimmed
    if isinstance(value, (int, float, bool)):
        report.coerced_keys.append(key)
        return str(value).strip()
    if isinstance(value, list):
        if any(isinstance(v, (dict, list)) for v in value):
            raise RepairError(
                f"dimension {key!r} is a nested list/object (un-repairable)"
            )
        report.coerced_keys.append(key)
        return "、".join(str(v).strip() for v in value if str(v).strip())
    raise RepairError(
        f"dimension {key!r} has un-repairable type {type(value).__name__}"
    )


def repair_generation(
    raw: str,
    *,
    expected_keys: list[str],
    chinese_dimensions: set[str] | None = None,
) -> tuple[dict[str, str], RepairReport]:
    """Repair raw LLM output to ``{expected_key: content}`` — or raise.

    ``expected_keys`` are the dimension labels the gap is missing (the schema the
    generation MUST cover). ``chinese_dimensions`` is the subset whose CONTENT
    must be Chinese (the English-leakage check applies to these); defaults to all
    expected keys (every generated dimension value is Chinese, source-faithful).

    Returns ``(repaired_map, report)`` where ``repaired_map`` covers EXACTLY the
    expected keys (extra keys dropped + recorded, every expected key present and
    non-empty). Raises :class:`RepairError` if any expected key is missing /
    empty after repair, if a value is un-repairable, or if a Chinese dimension's
    value is English-leakage that cannot be salvaged. NEVER returns a partial map
    on failure and NEVER silently drops an expected dimension.
    """
    if not expected_keys:
        raise RepairError("no expected dimensions to generate (empty schema)")
    chinese = set(chinese_dimensions) if chinese_dimensions is not None else set(expected_keys)
    report = RepairReport()

    text = _strip_fence(raw, report)
    obj_text = _extract_json_object(text, report)
    data = _load_json(obj_text, report)

    expected = set(expected_keys)
    repaired: dict[str, str] = {}

    # Coerce/keep the expected keys; record any extra keys as dropped (NOT silent).
    for key in expected_keys:  # preserve the caller's order (C6 declaration order)
        if key not in data:
            raise RepairError(
                f"required dimension {key!r} missing from output (no silent drop)"
            )
        content = _coerce_value(key, data[key], report)
        if not content:
            raise RepairError(f"required dimension {key!r} is empty after repair")
        if key in chinese and cjk_ratio(content) < _MIN_CJK_RATIO:
            # DEFERRED-046: reject ANY low-CJK value for a Chinese dimension,
            # regardless of Latin presence. The old `has_english_leakage` gate
            # early-returned False on no-Latin text, so a numeric/punctuation
            # hallucination (e.g. {"历史":123} -> "123", cjk_ratio 0) slipped
            # through as a "Chinese source-faithful" fact. cjk_ratio < min now
            # catches BOTH English prose AND non-Latin garbage.
            kind = "English-leakage" if has_english_leakage(content) else "non-Chinese (low-CJK)"
            raise RepairError(
                f"dimension {key!r} is {kind} "
                f"(cjk_ratio={cjk_ratio(content):.2f} < {_MIN_CJK_RATIO}); "
                "required Chinese content not produced"
            )
        repaired[key] = content

    for key in data:
        if key not in expected:
            report.dropped_keys.append(str(key))

    return repaired, report
