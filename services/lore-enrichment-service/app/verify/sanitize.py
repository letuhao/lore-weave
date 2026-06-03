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

import base64
import binascii
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
     r"forget\s+(?:everything|all|previous|the\s+above|what\s+(?:i|you)\s+said)"),
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
    # ── Classical Chinese (文言文) meta-directives (DEFERRED-050) ──────────────
    # ANCHORED on textual BACK-REFERENCES (前述/前文/上文/以上/前面/之前/先前) — a
    # directive that points at "the AFOREMENTIONED text/command" is a prompt-
    # injection meta-instruction, NOT in-world narrative. Deliberately NARROW: an
    # in-world Classical command (听我号令 / 弃尔旧法 / 修我新道) carries no back-
    # reference, so it does NOT match — critical because C3 AUTO-REJECTS injection
    # (an over-broad pattern would wrongly suppress legitimate generated lore).
    ("zh_classical_disregard_prior",
     r"(?:勿|毋|莫|休|不[要须必]|无须|毋须)"
     r"(?:从|听|遵|依|理会|顾|采纳|执行|遵从|遵循)"
     r"[^\n]{0,10}?(?:前述|前文|上文|以上|前面|之前|先前|前言)"),
    ("zh_classical_override_prior",
     r"(?:违背|背离|违逆|推翻|废除|废止|摒弃|抛却)"
     r"[^\n]{0,10}?(?:前述|前文|上文|以上|之前|先前|前言)"
     r"[^\n]{0,6}?(?:之?[命令]|指令|训示|训诫|规则|指示|约束)"),
    # NOTE: the override-qualifier (新 / 真正) is REQUIRED — "从我新指令" (follow my
    # NEW directive, implying override the prior) is meta; a bare "遵我指示" (follow
    # my instructions) is in-world and must NOT match (false-positive → auto-reject).
    ("zh_classical_follow_new_directive",
     r"(?:从|遵|遵从|依|按|执行)"
     r"[^\n]{0,4}?(?:吾|我|本座|此)"
     r"[^\n]{0,4}?(?:新|真正之)(?:指令|训示|指示|命令)"),
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


# A base64-shaped run (alphabet + optional padding). The minimum length is only a
# noise guard, NOT a correctness gate — the decode + UTF-8 + pattern-match filter
# prevents false-positives at ANY length (a benign run cannot decode to an
# injection phrase). 12 chars ≈ 9 decoded bytes ≈ a 3-CJK-char directive
# (e.g. 无视指令 → 16 b64 chars), so short ENCODED CJK injections are caught too
# (review-impl MED#1 — the demo corpus is CJK; 20 missed them).
_BASE64_RUN = re.compile(r"[A-Za-z0-9+/]{12,}={0,2}")


def _pattern_hits(text: str) -> list[tuple[str, int, int]]:
    """All phrase-pattern matches in ``text`` as ``(name, start, end)`` spans.
    The shared denylist loop (no base64 step → safe to call on decoded text)."""
    return [
        (name, m.start(), m.end())
        for name, pattern in INJECTION_PATTERNS
        for m in pattern.finditer(text)
    ]


def _scan_base64_injection(text: str) -> list[tuple[str, int, int]]:
    """Flag base64 runs whose DECODED content is itself injection (DEFERRED-050).

    An attacker can smuggle a directive past the phrase scan by base64-encoding it
    (``aWdub3Jl…`` = "ignore all previous instructions"). We decode each base64-
    shaped run and re-scan the DECODED text with the phrase patterns; the ENCODED
    run is flagged ONLY when the decode is valid UTF-8 AND contains injection — so
    benign base64 is never flagged (no false-positive → no wrongful C3 auto-reject).
    Re-scans with :func:`_pattern_hits` (NOT base64 again) so there is no recursion.
    """
    hits: list[tuple[str, int, int]] = []
    marker_len = len(FICTIONAL_MARKER)
    for m in _BASE64_RUN.finditer(text):
        # Idempotency: a run already preceded by the FICTIONAL marker (a prior
        # neutralize pass tagged it) must not re-fire — mirrors the phrase
        # patterns' lookbehind so a second neutralize call is a no-op.
        if text[max(0, m.start() - marker_len):m.start()] == FICTIONAL_MARKER:
            continue
        run = m.group(0)
        try:
            decoded_bytes = base64.b64decode(run, validate=True)
            decoded = decoded_bytes.decode("utf-8")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            continue  # not valid base64 / not UTF-8 → treat as opaque data
        if not decoded.strip():
            continue
        if _pattern_hits(_prenormalize(decoded)):
            hits.append(("base64_injection", m.start(), m.end()))
    return hits


def scan_injection(text: str | None) -> list[tuple[str, int, int]]:
    """Return every injection match as ``(pattern_name, start, end)`` spans.

    Spans are offsets into the PRE-NORMALIZED text (the text
    :func:`neutralize_proposal_text` tags). Empty/None input → ``[]``. Includes
    base64-smuggled injection (DEFERRED-050). Used by the verifier to build
    per-field injection evidence without mutating the text.
    """
    if not text:
        return []
    norm = _prenormalize(text)
    return _pattern_hits(norm) + _scan_base64_injection(norm)


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

    # Pass 1 — collect all match spans on the normalized text (phrase patterns +
    # base64-smuggled injection, DEFERRED-050).
    all_hits = _pattern_hits(norm) + _scan_base64_injection(norm)
    matches = [(start, end) for _name, start, end in all_hits]
    total_hits = len(matches)

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
