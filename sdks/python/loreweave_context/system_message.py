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

# Anthropic prompt-cache marker applied to the cacheable (message-independent-prefix) blocks.
_EPHEMERAL: dict = {"type": "ephemeral"}


def _text(text: str, *, cached: bool) -> dict:
    part: dict = {"type": "text", "text": text}
    if cached:
        part["cache_control"] = _EPHEMERAL
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
    skipped. In the cache path every tail block is cacheable; grounding is split into a
    cached `stable` prefix + an uncached `volatile` tail (K18.9), and `wm_pinned` is the
    uncached primacy anchor. In the plain path grounding is the single concatenated
    `context`. Grounding + `system_prompt` are ``.strip()``'d; `wm_pinned` and tail blocks
    are used verbatim — matching the original ladders exactly.
    """
    if use_cache:
        parts: list[dict] = [_text(kctx_stable.strip(), cached=True)]
        volatile = kctx_volatile.strip()
        if volatile:
            parts.append(_text(volatile, cached=False))
        if wm_pinned:
            parts.append(_text(wm_pinned, cached=False))
        if system_prompt and system_prompt.strip():
            parts.append(_text(system_prompt.strip(), cached=True))
        for block in tail_blocks:
            if block:
                parts.append(_text(block, cached=True))
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
