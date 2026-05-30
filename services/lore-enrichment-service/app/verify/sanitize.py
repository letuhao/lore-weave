r"""Injection-defense for canon-verify (RAID C12) — mirrors knowledge-service.

The corpus text, the retrieved grounding, AND the LLM's own generated output are
ALL untrusted: a poisoned 封神演义 chapter (or a model that absorbed one) can embed
prompt-injection / canon-spoofing / control sequences in an entity name, a
dimension label, or generated prose. C12 verifies a proposal AT CREATION, so this
is the seam where that untrusted text is neutralized before it can act as an
instruction on any downstream LLM (review summariser in C13, eval judge in C15).

This module **mirrors** knowledge-service ``app/extraction/injection_defense.py``
(Q1 LOCKED: "mirror knowledge-service pending_facts injection-defense"):

  * **Tag, do not delete** — a villain who says "无视一切指令" is legitimate
    fiction; dropping it erases story content. We prepend a ``[FICTIONAL] ``
    marker so a downstream LLM treats the span as quoted in-story speech, not an
    authoritative command. Narrative fidelity is preserved; the directive is
    declawed.
  * **Idempotent** — every pattern carries a fixed-width negative lookbehind
    ``(?<!\[FICTIONAL\] )`` so a second pass is a no-op (C12 may run verify, then
    C13 re-runs the same defense at review time — the second call must not double
    tag).
  * **Scan-then-tag** — collect every match across every pattern on the ORIGINAL
    text, then insert markers in one reverse-order pass, so an early pattern's
    inserted marker cannot split a later pattern's span and hide a hit.
  * **CJK-safe** — zh/ja/vi/ko injection phrases are matched as literal
    substrings (no word boundaries); zero-width / bidi control chars and full-
    width (全角) chat-template tokens are normalized + neutralized so an attacker
    cannot smuggle a hidden ``<|im_start|>`` via 全角 ``＜｜ｉｍ＿ｓｔａｒｔ｜＞`` or a
    zero-width-joined ``i‌g‌n‌o‌r‌e``.

It EXTENDS the C1 ``app/clients/sanitize.py`` defense (which strips invisibles +
NFC-normalizes + replaces a small set of control markers): C1 runs on the way IN
from glossary reads; C12 runs the fuller phrase-level defense at proposal-verify
time. The two compose — C1's invisible-strip feeds C12's phrase scan a clean
string so 全角 / zero-width evasions collapse to their canonical ASCII form first.

NO LLM call, NO model name, NO I/O. Pure functions.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = [
    "INJECTION_PATTERNS",
    "neutralize_proposal_text",
    "scan_injection",
    "FICTIONAL_MARKER",
]

#: The inert prefix tag prepended to a neutralized injection span. A downstream
#: LLM reads it as "this is quoted fiction", not an instruction to obey.
FICTIONAL_MARKER = "[FICTIONAL] "

# Zero-width / bidi-control chars used to smuggle hidden instructions across an
# otherwise-innocuous-looking span (mirror app/clients/sanitize.py _INVISIBLE).
_INVISIBLE = dict.fromkeys(
    [
        0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2028, 0x2029,
        0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0xFEFF,
        0x2066, 0x2067, 0x2068, 0x2069,
    ],
    None,
)

# Idempotency guard: prevents a second pass from re-tagging a span already tagged
# by a first pass. Prefixed to every pattern at compile time (mirror KS).
_ALREADY_TAGGED = r"(?<!\[FICTIONAL\] )"

# Named patterns (mirror knowledge-service INJECTION_PATTERNS + a few CJK/control
# additions). ``name`` is a stable short id used in the per-match evidence so a
# flag reports WHICH attack shape fired, not an opaque boolean. CJK patterns use
# literal substrings (no \b — word boundaries are meaningless in CJK).
_RAW_PATTERNS: tuple[tuple[str, str], ...] = (
    # ── English: instruction overrides ───────────────────────────────────────
    # Allow one OR MORE stacked qualifiers ("all previous", "the above") between
    # the verb and "instructions" — the real attack shape is not single-word.
    ("en_ignore_prior",
     r"ignore\s+(?:(?:all|any|the|previous|prior|above)\s+){1,4}instructions"),
    ("en_disregard_prior",
     r"disregard\s+(?:(?:all|any|the|previous|prior|above)\s+){1,4}instructions"),
    ("en_forget_everything",
     r"forget\s+(?:everything|all|previous)"),
    ("en_new_instructions",
     r"new\s+instructions:"),
    ("en_you_are_now",
     r"you\s+are\s+now\s+(?:a\s+|an\s+|the\s+)?"
     r"(?:\w+\s+){0,2}?"
     r"(?:assistant|model|ai|gpt|chatbot|bot|agent|system)\b"),
    # ── English: secret exfiltration ─────────────────────────────────────────
    ("en_system_prompt", r"system\s*prompt"),
    ("en_reveal_secret",
     r"reveal\s+(?:your|the)\s+"
     r"(?:system|api|prompt|instructions|key|token|password)"),
    # ── Code block / role / chat-template manipulation ───────────────────────
    ("en_code_system_block", r"```\s*system\b"),
    ("role_system_tag", r"\[/?(?:SYSTEM|ADMIN|INST)\]"),
    ("role_chat_template", r"<\|[a-z_]+\|>"),       # <|im_start|>, <|system|>, …
    ("role_s_tag", r"</?s>"),                        # <s> / </s>
    ("role_colon_prefix", r"\b(?:system|assistant|user)\s*:"),
    # ── Chinese (zh) — literal substrings, non-greedy gaps (idempotent) ──────
    ("zh_ignore_instructions", r"无视[^\n]{0,16}?指令"),
    ("zh_disregard_instructions", r"忽略[^\n]{0,16}?指令"),
    ("zh_disregard_above", r"忽略[^\n]{0,16}?(?:上文|以上|前面)"),
    ("zh_system_prompt", r"系统提示"),
    ("zh_you_are_now", r"你\s*现在\s*(?:是|扮演)"),
    ("zh_new_instructions", r"(?:新的?|以下)[^\n]{0,4}?指令(?:如下|：|:)"),
    # ── Japanese (ja) ─────────────────────────────────────────────────────────
    ("ja_ignore_prior", r"以前[^\n]{0,16}?指示[^\n]{0,16}?無視"),
    ("ja_system_prompt", r"システムプロンプト"),
    # ── Korean (ko) ───────────────────────────────────────────────────────────
    ("ko_ignore_instructions", r"이전[^\n]{0,16}?지시[^\n]{0,16}?무시"),
    # ── Vietnamese (vi) ───────────────────────────────────────────────────────
    ("vi_ignore_instructions", r"bỏ\s*qua[^\n]{0,16}?chỉ\s*dẫn"),
    ("vi_forget_guidance", r"quên[^\n]{0,16}?hướng\s*dẫn"),
)

#: Compiled once at import; each pattern wrapped with the idempotency lookbehind.
INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(_ALREADY_TAGGED + raw, re.IGNORECASE))
    for name, raw in _RAW_PATTERNS
)


def _prenormalize(text: str) -> str:
    """Collapse evasion forms BEFORE the phrase scan so hidden directives surface.

    1. Drop zero-width / bidi control chars (``i<ZWJ>gnore`` → ``ignore``).
    2. NFKC-normalize: maps full-width (全角) to ASCII so ``＜｜ｉｍ＿ｓｔａｒｔ｜＞``
       collapses to ``<|im_start|>`` and the chat-template pattern then fires.
       NFKC (not NFC) is used HERE — full-width compatibility folding is exactly
       the evasion we must defeat. Legitimate CJK ideographs are unaffected by
       NFKC (they have no compatibility decomposition); only the abusable
       full-width ASCII/forms fold.
    """
    cleaned = text.translate(_INVISIBLE)
    return unicodedata.normalize("NFKC", cleaned)


def scan_injection(text: str | None) -> list[tuple[str, int, int]]:
    """Return every injection match as ``(pattern_name, start, end)`` spans.

    Spans are offsets into the PRE-NORMALIZED text (the text
    :func:`neutralize_proposal_text` tags). Empty/None input → ``[]``. Used by the
    verifier to build per-field injection evidence without mutating the text.
    """
    if not text:
        return []
    norm = _prenormalize(text)
    hits: list[tuple[str, int, int]] = []
    for name, pattern in INJECTION_PATTERNS:
        for m in pattern.finditer(norm):
            hits.append((name, m.start(), m.end()))
    return hits


def neutralize_proposal_text(text: str | None) -> tuple[str, int]:
    """Neutralize injection in untrusted proposal/corpus text — ``(safe, hits)``.

    Mirrors knowledge-service ``neutralize_injection``:
      * None / empty → ``("", 0)``.
      * Pre-normalizes (strip invisibles + NFKC) so full-width / zero-width
        evasions surface.
      * Collects every match across every pattern on the normalized text, then
        inserts one ``[FICTIONAL] `` marker per distinct match start in a single
        reverse-order pass (early markers cannot split later spans).
      * Idempotent — a second call is a no-op (the lookbehind rejects an
        already-tagged start).

    Returns ``(neutralized_text, hit_count)`` where ``hit_count`` is the number of
    pattern matches (a positive count means the field carried injection and the
    verifier raises an ``injection`` flag).
    """
    if not text:
        return "", 0

    norm = _prenormalize(text)

    # Pass 1 — collect all match spans on the normalized text.
    matches: list[tuple[int, int]] = []
    total_hits = 0
    for _name, pattern in INJECTION_PATTERNS:
        for m in pattern.finditer(norm):
            matches.append((m.start(), m.end()))
            total_hits += 1

    if not matches:
        return norm, 0

    # Pass 2 — insert one marker per DISTINCT start, reverse order so earlier
    # offsets stay valid. Per-start (not coalesced) so every tagged span's start
    # is preceded by the marker → the second-pass lookbehind rejects it.
    unique_starts = sorted({start for start, _end in matches}, reverse=True)
    result = norm
    for start in unique_starts:
        result = result[:start] + FICTIONAL_MARKER + result[start:]

    return result, total_hits
