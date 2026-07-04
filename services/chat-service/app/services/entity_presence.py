"""T5 (Context Budget Law D2) — entity-presence intent gate (heuristic, NO LLM).

The expensive per-turn grounding pull (`knowledge_client.build_context` retrieving
5 passages + 12 entities) is wasted on a turn that references zero book lore
("what can you help me with?", "give me a 3-step plan"). D2 gates it on a single
cheap question: **does the message contain a known glossary/entity token for this
book?** — NOT a surface-verb heuristic (which false-negatives on "change status of
*Lâm Uyển's arc*"). Entity-presence catches the entity token regardless of verb.

Design rules (spec §D2, §D4):
  - **Heuristic-only.** No model call — sidesteps the empty-`user_default_models`
    provider trap and stays sub-millisecond.
  - **Bias to include.** When we cannot tell (no entity set available, or the
    message is a bare pronoun/short follow-up that may refer to loaded lore), the
    gate OPENS (grounding proceeds). We only gate OUT when we are confident the
    turn is lore-free. A false-negative (dropping needed lore) is far worse than a
    false-positive (a cheap turn that over-fetches).
  - The gate governs ONLY the expensive pull. The always-on Core Memory Blocks
    (`story_state`) still project every turn as the safety net (D4) — so even a
    gated-out follow-up keeps its lore.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Two families of no-entity-token turns that must STILL open the gate
# (bias-to-include), because a false-negative strips lore the answer needs:
#
#  1. ANAPHORA — a follow-up like "make it darker" / "그거" leans on lore already in
#     play. (The story_state block (D4) is a safety net, but a cold anaphor may still
#     want the fuller pull.)
#  2. LORE-INTENT — a DISCOVERY question that references lore the user can't yet name:
#     "who is the main character", "tell me about the protagonist", "what happens in
#     this story". These carry no known entity token (the user is asking BECAUSE they
#     don't know it) yet clearly need grounding. Verb/keyword phrasing catches them.
#
# Both are deliberately broad — over-including a cheap turn costs a few tokens; under-
# including a lore turn costs a confident-wrong answer. We err toward grounding.
_ANAPHORA = re.compile(
    r"\b(it|its|it's|that|this|they|them|their|he|she|him|her|his|the (?:scene|chapter|character|arc|story))\b",
    re.IGNORECASE,
)
_LORE_INTENT = re.compile(
    r"\b("
    r"main character|protagonist|antagonist|the villain|the hero(?:ine)?|"
    r"the (?:book|story|plot|world|setting|cast|lore|timeline|characters?)|"
    r"who (?:is|are|was|were)|what happens|tell me about|"
    r"summar(?:y|ize|ise)|recap|so far|remind me"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EntityPresence:
    """The gate decision + the evidence the Inspector/telemetry surfaces."""

    grounding_needed: bool
    matched: tuple[str, ...] = field(default_factory=tuple)
    reason: str = ""

    def as_telemetry(self) -> dict:
        """The `entity_presence` field of the contextBudget frame (spec checklist)."""
        return {
            "grounding_needed": self.grounding_needed,
            "matched": list(self.matched),
            "reason": self.reason,
        }


def _token_pattern(token: str) -> re.Pattern[str]:
    """Word-boundary match for ASCII tokens (so 'arc' doesn't hit 'search'); plain
    substring for tokens with non-ASCII (CJK has no word boundaries) or spaces."""
    t = token.strip()
    if t.isascii() and " " not in t:
        return re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE)
    return re.compile(re.escape(t), re.IGNORECASE)


def _has_anaphora(message: str) -> bool:
    return bool(_ANAPHORA.search(message))


def _has_lore_intent(message: str) -> bool:
    return bool(_LORE_INTENT.search(message))


def detect_entity_presence(
    message: str,
    entity_tokens: frozenset[str] | set[str] | None,
) -> EntityPresence:
    """Decide whether `message` warrants the expensive grounding pull.

    `entity_tokens` is the book's known-entity name+alias set (lowercased is fine;
    matching is case-insensitive). `None`/empty ⇒ we cannot tell ⇒ gate OPENS.
    """
    msg = (message or "").strip()
    if not msg:
        # An empty turn (shouldn't happen) → open, harmless.
        return EntityPresence(True, reason="empty_message")
    if not entity_tokens:
        return EntityPresence(True, reason="no_entity_set")  # bias-to-include

    matched: list[str] = []
    for tok in entity_tokens:
        if not tok or not tok.strip():
            continue
        if _token_pattern(tok).search(msg):
            matched.append(tok.strip())
            if len(matched) >= 8:  # enough evidence; don't scan the whole book
                break
    if matched:
        return EntityPresence(True, tuple(sorted(set(matched))), reason="entity_match")

    # No entity token — but a DISCOVERY question references lore the user can't name
    # yet ("who is the main character") → it needs grounding.
    if _has_lore_intent(msg):
        return EntityPresence(True, reason="lore_intent_bias_include")

    # …or an anaphoric follow-up leaning on lore already loaded.
    if _has_anaphora(msg):
        return EntityPresence(True, reason="anaphora_bias_include")

    # Confident lore-free op (no entity, no anaphora, no lore-intent) → gate OUT.
    return EntityPresence(False, reason="no_entity_no_anaphora")
