"""English intent keywords — VERBATIM from the original classifier.py regexes so
English routing stays byte-identical. Latin script ⇒ `\\b`-bounded by the registry.

Each constant is a regex-alternation BODY (no surrounding `\\b` or group — the
registry wraps Latin modules in one shared `\\b(?:…)\\b`)."""

from __future__ import annotations

# Strong past anchors — win even when an entity is present. Bare "used to" is
# idiomatic, so require a following be/have/live/exist/rule/serve.
HISTORICAL_STRONG = (
    r"back when|long ago|years? ago|chapters? ago|originally|"
    r"at first|in the beginning|used to (be|have|live|exist|rule|serve)|"
    r"was once"
)

# Weak past anchors — only win when NO specific entity is present.
HISTORICAL_WEAK = r"before|earlier in|previously"

# Present/near-past anchors. Bare "just" banned (too idiomatic) — require a
# temporal companion.
RECENT = (
    r"just (now|happened|arrived|said|did|finished)|"
    r"right now|at the moment|currently|this chapter|"
    r"a moment ago|happening now|right here|present moment"
)

# Relational keywords — only meaningful when ≥2 entities present.
RELATIONAL_KEYWORDS = (
    r"know|knew|meet|met|related|between|together|"
    r"connection|relationship|friends?|enemies|enemy|"
    r"married|allied|rival|how are"
)

# Very explicit relational phrasings — win even with 1 entity present.
RELATIONAL_STRONG = (
    r"relationship between|how does .* know|how are .* and|"
    r"who knows|who met|connection between"
)
