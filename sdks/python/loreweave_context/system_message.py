"""The system-message assembly renderer (Context Budget Law A1, T3.1).

chat-service built the system prompt TWICE in lockstep — an Anthropic cache path (a
`list[dict]` with `cache_control` markers) and a plain-string path — 12 blocks in identical
order in two independent `if` ladders. A block added to one and not the other silently
diverges. This is the single source of truth: build the ordered `tail_blocks` list ONCE and
render it either way. Output is BYTE-IDENTICAL to the two original ladders (golden-tested).

Pure string logic; no I/O, no provider SDK.
"""
from __future__ import annotations

from collections.abc import Sequence

def _text(text: str, *, cached: bool) -> dict:
    part: dict = {"type": "text", "text": text}
    if cached:
        # A FRESH marker per part (matching the original ladder) — never a shared dict, so
        # no aliasing between parts if a caller ever mutates one.
        part["cache_control"] = {"type": "ephemeral"}
    return part


def build_system_message(
    *,
    use_cache: bool,
    kctx_context: str,
    kctx_stable: str,
    kctx_volatile: str,
    wm_pinned: str | None,
    system_prompt: str | None,
    tail_blocks: Sequence[str | None],
) -> str | list[dict] | None:
    """Render the system message CONTENT — a `list[dict]` (Anthropic cache path) or a
    ``"\\n\\n"``-joined `str` (plain path), or ``None`` when the plain path has nothing to
    insert. The caller decides `use_cache` (Anthropic + non-empty stable context) and does the
    ``messages.insert(0, {"role": "system", "content": <this>})``.

    `tail_blocks` is the ordered post-system-prompt block list (steering, the built-in +
    user skills, plan-mode nudge, skill catalog, book note); ``None``/empty entries are
    skipped. In the cache path the whole stable persona+tail region is cached by a SINGLE
    breakpoint on its last block (Anthropic caches the cumulative prefix, and caps
    cache_control at 4 blocks); grounding is split into a cached `stable` prefix + an
    uncached `volatile` tail (K18.9), and `wm_pinned` is the uncached primacy anchor. So the
    request carries exactly 2 breakpoints (stable-memory + end-of-tail). In the plain path
    grounding is the single concatenated
    `context`. Grounding + `system_prompt` are ``.strip()``'d; `wm_pinned` and tail blocks
    are used verbatim — matching the original ladders exactly.
    """
    if use_cache:
        parts: list[dict] = [_text(kctx_stable.strip(), cached=True)]  # BP1: stable-memory prefix
        volatile = kctx_volatile.strip()
        if volatile:
            parts.append(_text(volatile, cached=False))
        if wm_pinned:
            parts.append(_text(wm_pinned, cached=False))
        # The stable post-grounding region (persona system_prompt + every tail block) gets
        # exactly ONE cache breakpoint, at its END. Anthropic caches the CUMULATIVE prefix up
        # to a breakpoint, so a single marker on the last block caches the whole region — the
        # per-block markers the original ladder emitted were redundant AND, worse, blew past
        # Anthropic's HARD max of 4 cache_control blocks: a book-scoped turn (2 + 9 tail = 11
        # markers) got a 400 "A maximum of 4 blocks can be marked with cache_control", so
        # caching was BROKEN (the whole request failed) for Claude book turns. Two breakpoints
        # total — stable-memory (BP1) + end-of-stable-tail (BP2) — which is exactly what
        # stream_service documents. See test_cache_never_exceeds_anthropic_4_breakpoints.
        stable_region: list[dict] = []
        if system_prompt and system_prompt.strip():
            stable_region.append(_text(system_prompt.strip(), cached=False))
        for block in tail_blocks:
            if block:
                stable_region.append(_text(block, cached=False))
        if stable_region:
            stable_region[-1]["cache_control"] = {"type": "ephemeral"}  # BP2
        parts.extend(stable_region)
        return parts

    system_parts: list[str] = []
    if kctx_context:
        stripped = kctx_context.strip()
        if stripped:
            system_parts.append(stripped)
    if wm_pinned:
        system_parts.append(wm_pinned)
    if system_prompt:
        stripped = system_prompt.strip()
        if stripped:
            system_parts.append(stripped)
    for block in tail_blocks:
        if block:
            system_parts.append(block)
    return "\n\n".join(system_parts) if system_parts else None
