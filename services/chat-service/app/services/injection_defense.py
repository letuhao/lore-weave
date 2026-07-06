"""P0-5 (audit Area 3, SEC-4 / ML-4) — indirect prompt-injection defense.

chat-service splices the book/graph/knowledge block that knowledge-service returns
from `build_context` (retrieved memory, glossary, passages, facts, graph text — and
the roleplay working-memory anchor) into the assembled LLM prompt. That content is
UNTRUSTED: it is LLM-generated or user-authored fiction, so it can carry indirect
prompt-injection (e.g. a villain's line "ignore all previous instructions", or a
smuggled `<|im_start|>system` / zero-width / base64 payload). Relying only on the
knowledge-skill prompt convention + the human review gate is not enough — the model
must be handed that text as DATA, not instructions.

This module neutralizes injection in the retrieved text at the point it enters the
prompt, mirroring how knowledge-service defends its extraction path
(`app/extraction/injection_defense.py`). It delegates to the shared, multilingual
(en / zh incl. 文言文 / ja / ko / vi) SDK defense in `loreweave_grounding.sanitize`,
which is Unicode-aware (NFKC + zero-width strip + base64 decode-scan).

Contract, matching knowledge-service's shim:
  * ONLY injected/retrieved content is sanitized — NEVER the user's own message and
    NEVER the user's own session persona/system prompt (that is their input).
  * CLEAN text is returned byte-for-byte UNCHANGED (no NFKC fold), so a block with
    no injection keeps its legitimate multilingual (CJK / Vietnamese) content exactly.
  * A FLAGGED block is normalized in FULL — the whole block is de-obfuscated (NFKC +
    zero-width/bidi strip) and the injection spans tagged with the inert
    `[FICTIONAL] ` marker. So legit content that happens to share a flagged block may
    be Unicode-normalized (e.g. full-width→half-width); this is acceptable because a
    block carrying an injection is already suspect, and canonical CJK ideographs are
    unchanged by NFKC. (Span-precise splicing that leaves un-flagged bytes untouched
    is a deferred SDK enhancement — see the audit backlog.)
  * Idempotent (the SDK's lookbehind guard) and None/empty-safe.
"""

from __future__ import annotations

from loreweave_grounding.sanitize import neutralize_proposal_text, scan_injection

__all__ = ["neutralize_injection"]


def neutralize_injection(text: str | None) -> str:
    """Tag any injection spans in untrusted retrieved `text` — returns safe text.

    Clean text → returned byte-for-byte unchanged (no NFKC fold). A block that
    flags → normalized in full (NFKC + zero-width strip) with the injection spans
    `[FICTIONAL] `-tagged. None/empty → `""`. See the module docstring.
    """
    if not text:
        return ""
    # Clean text → return the RAW input unchanged (do NOT NFKC-normalize legit
    # multilingual text). Only flagged text is de-obfuscated + tagged. This mirrors
    # knowledge-service's `neutralize_injection` clean-text-unchanged contract.
    if not scan_injection(text):
        return text
    safe, _hits = neutralize_proposal_text(text)
    return safe
