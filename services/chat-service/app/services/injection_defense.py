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
  * Clean text is returned UNCHANGED (raw, not NFKC-folded) so legitimate
    multilingual (CJK / Vietnamese) content is never mangled. Only text that
    actually flags is de-obfuscated + tagged with the inert `[FICTIONAL] ` marker.
  * Idempotent (the SDK's lookbehind guard) and None/empty-safe.
"""

from __future__ import annotations

from loreweave_grounding.sanitize import neutralize_proposal_text, scan_injection

__all__ = ["neutralize_injection"]


def neutralize_injection(text: str | None) -> str:
    """Tag any injection spans in untrusted retrieved `text` — returns safe text.

    Returns the input unchanged when it is clean (no NFKC folding of legitimate
    multilingual content); only flagged spans are de-obfuscated + `[FICTIONAL] `
    tagged. None/empty → `""`.
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
