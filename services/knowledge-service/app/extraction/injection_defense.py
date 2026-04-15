"""K15.6 — prompt injection neutralizer (KSA §5.1.5 Defense 2).

Pure function, no I/O except a Prometheus counter increment per
pattern hit. Scans text for well-known prompt-injection phrases
and prepends a `[FICTIONAL] ` marker so a downstream LLM can treat
the phrase as in-story dialogue rather than a command.

**Why not delete the content.** Narrative fidelity matters: a
chapter that has a villain say "ignore all previous instructions"
is a legitimate piece of fiction. Dropping the phrase would erase
story content; tagging it tells the LLM it is quoted speech, not
an authoritative instruction directed at the model.

**Idempotent.** Every pattern has a fixed-width lookbehind
`(?<!\\[FICTIONAL\\] )` so running `neutralize_injection` twice on
the same text produces the same output as running it once — the
KSA calls this function both at extraction time (K15.7 write) and
at context-build time (K18.7), so the second pass must be a no-op
on already-tagged content.

**Named patterns for observability.** Each regex is paired with a
stable short name used as the `pattern` label on the
`injection_pattern_matched_total` counter. Raw regex source would
be a cardinality disaster and unreadable in Grafana.

**What this module deliberately does NOT do:**
  - LLM-based injection detection — too expensive, Track 2
  - Content redaction — would break narrative fidelity
  - Semantic intent analysis — just pattern matching per KSA
  - Block the fact from being written — caller always writes

Reference: KSA §5.1.5, K15.6 plan row in
KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md.
"""

from __future__ import annotations

import re

from app.metrics import injection_pattern_matched_total

__all__ = [
    "INJECTION_PATTERNS",
    "neutralize_injection",
]


# Idempotency guard: a fixed-width negative lookbehind that prevents
# a second call from re-tagging content already tagged by a first
# call. Every pattern below gets this guard prefixed at compile time.
_ALREADY_TAGGED = r"(?<!\[FICTIONAL\] )"

# Patterns from KSA §5.1.5 plus a handful of common additions.
# `name` is a stable short ID used as the Prometheus label; keep
# them snake_case, language-prefixed, and ≤30 chars so Grafana
# filters stay legible.
#
# Format: (name, raw_regex). All patterns compile with IGNORECASE
# except the CJK ones where case is meaningless — IGNORECASE is
# harmless on them so we apply it uniformly.
_RAW_PATTERNS: tuple[tuple[str, str], ...] = (
    # ── English: instruction overrides ──────────────────────────────
    ("en_ignore_prior",
     r"ignore\s+(?:previous|prior|above|all)\s+instructions"),
    ("en_disregard_prior",
     r"disregard\s+(?:previous|prior|above|all)\s+instructions"),
    ("en_forget_everything",
     r"forget\s+(?:everything|all|previous)"),
    ("en_new_instructions",
     r"new\s+instructions:"),
    ("en_you_are_now",
     r"you\s+are\s+now\s+"),

    # ── English: secret exfiltration ────────────────────────────────
    ("en_system_prompt",
     r"system\s*prompt"),
    ("en_reveal_secret",
     r"reveal\s+(?:your|the)\s+"
     r"(?:system|api|prompt|instructions|key|token|password)"),

    # ── Code block / role manipulation ──────────────────────────────
    ("en_code_system_block", r"```\s*system\b"),
    ("role_system_tag", r"\[SYSTEM\]"),
    ("role_admin_tag", r"\[ADMIN\]"),
    ("role_im_start", r"<\|im_start\|>"),

    # ── Chinese (zh) — literal substrings, no \b (no word boundaries) ─
    # "无视...指令" = ignore ... instructions
    ("zh_ignore_instructions", r"无视[^\n]{0,16}指令"),
    # "忽略...指令" = disregard ... instructions (alt phrasing)
    ("zh_disregard_instructions", r"忽略[^\n]{0,16}指令"),
    # "系统提示" = system prompt
    ("zh_system_prompt", r"系统提示"),

    # ── Japanese (ja) ───────────────────────────────────────────────
    # "以前の...指示...無視" = ignore previous instructions
    ("ja_ignore_prior", r"以前[^\n]{0,16}指示[^\n]{0,16}無視"),
    # "システムプロンプト" = system prompt
    ("ja_system_prompt", r"システムプロンプト"),

    # ── Vietnamese (vi) ─────────────────────────────────────────────
    # "bỏ qua ... chỉ dẫn" = ignore ... instructions
    ("vi_ignore_instructions", r"bỏ\s*qua[^\n]{0,16}chỉ\s*dẫn"),
    # "quên ... hướng dẫn" = forget ... guidance
    ("vi_forget_guidance", r"quên[^\n]{0,16}hướng\s*dẫn"),
)


# Compile once at import time. Each pattern is wrapped with the
# idempotency lookbehind so a second pass is a no-op.
INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(_ALREADY_TAGGED + raw, re.IGNORECASE))
    for name, raw in _RAW_PATTERNS
)


def neutralize_injection(
    text: str,
    *,
    project_id: str | None = None,
) -> tuple[str, int]:
    """Tag injection phrases in `text` with a `[FICTIONAL] ` prefix.

    Args:
        text: raw user-derived content — a chapter paragraph, an
            extracted fact's `sentence` field, a chat turn. Empty /
            None input returns ("", 0).
        project_id: optional tenant ID for the metric label. Pass
            None for call sites without a project context (unit
            tests, orchestrator probes); the label becomes
            `"unknown"`.

    Returns:
        `(sanitized_text, hit_count)`. `hit_count` counts distinct
        pattern matches (not unique output insertions — overlapping
        matches from different patterns each count once for
        observability). The Prometheus counter
        `injection_pattern_matched_total` is incremented once per
        pattern hit with the pattern name as the `pattern` label.

    Idempotent: calling twice on the same input yields the same
    output as calling once. Each pattern's idempotency lookbehind
    (`(?<!\\[FICTIONAL\\] )`) rejects matches whose start is already
    tagged, so a second pass is a no-op.

    **Scan-then-tag design.** A naive sequential sub would let
    pattern A's inserted `[FICTIONAL] ` marker split pattern B's
    span, causing B's counter never to fire even though B's phrase
    is present — breaking the "metric incremented on detection"
    acceptance criterion. Instead we collect every match across
    every pattern on the original text, bump each counter, merge
    overlapping spans, and insert markers in a single reverse-order
    pass. K15.6-R1/I1.
    """
    if not text:
        return "", 0

    label_project = project_id or "unknown"

    # Pass 1 — collect all matches across all patterns on the
    # ORIGINAL text. Each entry is (start, end, pattern_name).
    # Counters are bumped here so overlapping-but-distinct matches
    # (e.g., "Reveal the system prompt" fires both en_reveal_secret
    # and en_system_prompt) are both observable.
    matches: list[tuple[int, int]] = []
    total_hits = 0
    for name, pattern in INJECTION_PATTERNS:
        count_for_pattern = 0
        for m in pattern.finditer(text):
            matches.append((m.start(), m.end()))
            count_for_pattern += 1
        if count_for_pattern:
            total_hits += count_for_pattern
            injection_pattern_matched_total.labels(
                project_id=label_project,
                pattern=name,
            ).inc(count_for_pattern)

    if not matches:
        return text, 0

    # Pass 2 — dedupe exact-duplicate start positions and insert
    # one `[FICTIONAL] ` marker per distinct match start, in reverse
    # order so earlier offsets stay valid.
    #
    # We deliberately do NOT merge overlapping spans. If we coalesced
    # `en_reveal_secret` [0, 17) and `en_system_prompt` [11, 24) into
    # a single [0, 24) span with one marker at 0, the inner pattern's
    # start position at 11 would be preceded by "the " in the tagged
    # output, not by `[FICTIONAL] ` — so the idempotency lookbehind
    # wouldn't fire on a second call, and the inner pattern would be
    # re-matched and re-tagged on every pass. Per-match insertion
    # ensures every pattern start in the output has its marker
    # directly before it, so the second-pass lookbehind rejects it.
    # K15.6-R1 follow-up.
    unique_starts = sorted({start for start, _end in matches}, reverse=True)
    result = text
    for start in unique_starts:
        result = result[:start] + "[FICTIONAL] " + result[start:]

    return result, total_hits
