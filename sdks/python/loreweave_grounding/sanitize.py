r"""Injection-defense for grounding/verify — service-agnostic.

Lifted verbatim from lore-enrichment-service `app/verify/sanitize.py` (mui #3
grounding-port consolidation). Pure functions; NO LLM call, NO model name, NO
I/O. Tag-don't-delete (a villain who says "ignore all instructions" is
legitimate fiction); idempotent; scan-then-tag; CJK/zero-width/full-width safe.
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
# otherwise-innocuous-looking span.
_INVISIBLE = dict.fromkeys(
    [
        0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2028, 0x2029,
        0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0xFEFF,
        0x2066, 0x2067, 0x2068, 0x2069,
    ],
    None,
)

# Idempotency guard: prevents a second pass from re-tagging a span already tagged
# by a first pass. Prefixed to every pattern at compile time.
_ALREADY_TAGGED = r"(?<!\[FICTIONAL\] )"

# Named patterns. ``name`` is a stable short id used in the per-match evidence so
# a flag reports WHICH attack shape fired. CJK patterns use literal substrings.
_RAW_PATTERNS: tuple[tuple[str, str], ...] = (
    # ── English: instruction overrides ───────────────────────────────────────
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
    # ── Classical Chinese (文言文) meta-directives ─────────────────────────────
    ("zh_classical_disregard_prior",
     r"(?:勿|毋|莫|休|不[要须必]|无须|毋须)"
     r"(?:从|听|遵|依|理会|顾|采纳|执行|遵从|遵循)"
     r"[^\n]{0,10}?(?:前述|前文|上文|以上|前面|之前|先前|前言)"),
    ("zh_classical_override_prior",
     r"(?:违背|背离|违逆|推翻|废除|废止|摒弃|抛却)"
     r"[^\n]{0,10}?(?:前述|前文|上文|以上|之前|先前|前言)"
     r"[^\n]{0,6}?(?:之?[命令]|指令|训示|训诫|规则|指示|约束)"),
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
       collapses to ``<|im_start|>``. Legitimate CJK ideographs are unaffected.
    """
    cleaned = text.translate(_INVISIBLE)
    return unicodedata.normalize("NFKC", cleaned)


# A base64-shaped run (alphabet + optional padding). The min length is a noise
# guard, not a correctness gate — the decode + UTF-8 + pattern-match filter
# prevents false-positives at ANY length.
_BASE64_RUN = re.compile(r"[A-Za-z0-9+/]{12,}={0,2}")


def _pattern_hits(text: str) -> list[tuple[str, int, int]]:
    """All phrase-pattern matches in ``text`` as ``(name, start, end)`` spans."""
    return [
        (name, m.start(), m.end())
        for name, pattern in INJECTION_PATTERNS
        for m in pattern.finditer(text)
    ]


def _scan_base64_injection(text: str) -> list[tuple[str, int, int]]:
    """Flag base64 runs whose DECODED content is itself injection.

    Decode each base64-shaped run and re-scan the DECODED text; the ENCODED run
    is flagged ONLY when the decode is valid UTF-8 AND contains injection.
    """
    hits: list[tuple[str, int, int]] = []
    marker_len = len(FICTIONAL_MARKER)
    for m in _BASE64_RUN.finditer(text):
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

    Spans are offsets into the PRE-NORMALIZED text. Empty/None input → ``[]``.
    Includes base64-smuggled injection.
    """
    if not text:
        return []
    norm = _prenormalize(text)
    return _pattern_hits(norm) + _scan_base64_injection(norm)


def neutralize_proposal_text(text: str | None) -> tuple[str, int]:
    """Neutralize injection in untrusted text — ``(safe, hits)``.

    None/empty → ``("", 0)``. Pre-normalizes (strip invisibles + NFKC), collects
    every match, then inserts one ``[FICTIONAL] `` marker per distinct match
    start in a single reverse-order pass. Idempotent — a second call is a no-op.
    """
    if not text:
        return "", 0

    norm = _prenormalize(text)

    all_hits = _pattern_hits(norm) + _scan_base64_injection(norm)
    matches = [(start, end) for _name, start, end in all_hits]
    total_hits = len(matches)

    if not matches:
        return norm, 0

    unique_starts = sorted({start for start, _end in matches}, reverse=True)
    result = norm
    for start in unique_starts:
        result = result[:start] + FICTIONAL_MARKER + result[start:]

    return result, total_hits
