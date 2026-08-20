"""What is this turn ASKING FOR — to look, or to change? (R5 / R4 of surface-answerability)

🔴 THE INCIDENT, measured 5/5 on 2026-08-13 through the real FE path. The author asked *"Show me
the outline I've planned for this book — what chapters and scenes are in it?"* and the turn
CREATED three chapters in their book. `composition_outline_node_edit` is Tier A, so it should have
raised a confirm card; instead a standing "always allow" granted on 2026-07-30 — two weeks
earlier, during a session that was genuinely building — executed it silently.

A standing consent is granted in a context and then applies forever, in every context. That is the
defect: the author allowed a tool to write **while they were asking it to write**. Nothing about
that grant says "and also when I ask you to show me something."

So the mood of the REQUEST is a consent input, and this module computes it the same way
`user_abandoned_rail` computes its release: a literal match, no inference, no LLM.

**Conservative by construction, in two ways that matter:**

  1. It answers ``unknown`` unless it is confident, and ``unknown`` behaves exactly as today. A
     mood classifier that guesses would put a confirm card in front of writes the author plainly
     asked for, which trains them to click through cards — the opposite of consent.
  2. ``inspect`` requires an inspect marker AND the absence of any construct verb. "Show me the
     outline and add a chapter" is NOT an inspect turn; it is mixed, and mixed resolves to
     ``unknown`` so the standing grant still applies.

What it is NOT: a general intent classifier, and not a router. It decides one thing — whether a
turn is unambiguously a request to LOOK — because that is the only case where suppressing a
standing write-grant is obviously right.
"""
from __future__ import annotations

import re

#: Phrases that mark a request to LOOK. Deliberately verb-anchored rather than "ends with ?",
#: because "can you add a chapter?" is a question and a write.
_INSPECT = re.compile(
    r"\b(?:show|list|display)\s+(?:me\b|us\b|the\b|my\b|all\b|what\b)"
    r"|\bwhat(?:'s| is| are|\s+do|\s+does|\s+have)\b"
    r"|\bwhich\b"
    r"|\bhow many\b"
    r"|\b(?:tell|remind)\s+me\b"
    r"|\bdo i have\b"
    r"|\bcan i see\b"
    r"|\blet me see\b"
    r"|\bgive me (?:a |the )?(?:list|summary|rundown|overview)\b",
    re.I,
)

#: Any verb that asks for a CHANGE. Presence of one of these disqualifies `inspect` outright —
#: a mixed request must not have its standing write-grant suppressed.
_CONSTRUCT = re.compile(
    r"\b(?:add|create|make|write|draft|generate|build|set\s+up|setup"
    r"|update|edit|change|modify|revise|rewrite|fix"
    r"|delete|remove|drop|clear|archive"
    r"|rename|move|reorder|merge|split"
    r"|propose|apply|save|publish|import|translate)\b",
    re.I,
)

INSPECT = "inspect"
CONSTRUCT = "construct"
UNKNOWN = "unknown"


def request_mood(text: str | None) -> str:
    """``inspect`` | ``construct`` | ``unknown`` — what the user's own words asked for.

    ``inspect`` is only returned for an unambiguous look-request: an inspect marker AND no
    construct verb anywhere in the message. Everything else is ``construct`` (a construct verb is
    present) or ``unknown`` (neither marker), and both of those leave every existing behaviour
    untouched.
    """
    if not text:
        return UNKNOWN
    constructs = bool(_CONSTRUCT.search(text))
    inspects = bool(_INSPECT.search(text))
    if inspects and not constructs:
        return INSPECT
    if constructs and not inspects:
        return CONSTRUCT
    return UNKNOWN


def standing_grant_applies(mood: str, *, kind: str) -> bool:
    """Does a standing "always allow" apply to THIS turn, for this consent axis?

    Only the ``mutation`` axis is moderated, and only on an unambiguous ``inspect`` turn: the
    author asked to look, so a two-week-old grant to WRITE is not consent for what is about to
    happen. The call still runs — it just has to ask, which is what the Tier-A gate exists for.

    ``spend`` is deliberately NOT moderated here. A paid READ is a normal thing to do on an
    inspect turn, and suppressing that grant would prompt for something the author is plainly
    asking for. Different axis, different answer — the two consents are orthogonal by design.
    """
    return not (kind == "mutation" and mood == INSPECT)
