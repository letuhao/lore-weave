# Entity Extraction

You are a precise information extractor for a novel / fiction knowledge
graph. Extract named entities from the TEXT below and return them as
strict JSON conforming to the schema.

TEXT may be in any language (English, Vietnamese, Chinese, or mixed).
Keep entity `name` values in the ORIGINAL script of TEXT — do not
transliterate or translate. JSON keys and `kind` values stay English.

## Input

TEXT:
```
{text}
```

KNOWN_ENTITIES (already canonicalized — prefer exact matches over new
names; empty if none):
```
{known_entities}
```

## Output schema

Return a single JSON object and nothing else — no prose, no markdown
fences, no trailing commentary. Shape:

```json
{{
  "entities": [
    {{
      "name": "string — canonical display name as it appears in TEXT",
      "kind": "person | place | organization | artifact | concept | other",
      "aliases": ["string"],
      "confidence": 0.0
    }}
  ]
}}
```

## Rules

1. **Only real mentions.** Do not extract entities merely *implied*
   by TEXT. "The king was angry" without a name is not a person entity.
2. **Fold duplicates.** If the same entity appears multiple times,
   emit one object and collect alternate spellings in `aliases`.
3. **Reported speech ≠ assertion.** "Alice said Bob is a spy" extracts
   both Alice and Bob as persons, but does NOT assert Bob's occupation.
4. **Hypothetical ≠ assertion.** "If Kai goes to Harbin..." extracts
   Kai as a person but NOT Harbin as a visited place.
5. **Known entities win ties.** If a name matches an entry in
   KNOWN_ENTITIES (case-insensitive, whitespace-normalized), use the
   canonical spelling from KNOWN_ENTITIES verbatim.
6. **Confidence ∈ [0.5, 1.0].** 1.0 for unambiguous proper nouns
   with capitalized spelling and clear context; 0.5 for borderline
   cases you're emitting anyway. Below 0.5, omit the entity.
7. **Kind fallback.** If none of {{person, place, organization,
   artifact, concept}} fit, use "other". Do not invent new kinds.
8. **Scene-relevance filter.** Extract entities that play a role in
   the chapter — present in scenes, speaking, acting, being addressed,
   or being the subject of the chapter's events / concerns. **DO NOT
   extract entities mentioned only as:**
   - Geographic asides not used as a scene setting (e.g., "estates
     extended into Berkshire and Hampshire" — list these as background,
     omit them)
   - Backstory references to past events outside this chapter
     (e.g., "years ago in Calcutta he beat his native butler" — omit
     Calcutta and butler)
   - Comparison or anecdote names (e.g., "like Mrs. Farintosh's prior
     case" — omit Mrs. Farintosh)
   - Decorative places, regiments, or organizations not visited /
     interacted with in this chapter ("near Crewe", "the Bengal
     Artillery regiment" — omit)

   When in doubt, ask: "does this entity participate in any current-
   chapter event or scene, OR is it the subject of this chapter's
   concerns?" If neither, omit. **Bias toward omission for backstory
   mentions** — under-extraction of background details is preferable
   to filling the graph with one-off mentions.

## Example A — basic schema

TEXT: "Kai left Harbin for the Imperial Academy carrying the Jade Seal."
KNOWN_ENTITIES: ["Kai"]

Output:
```json
{{
  "entities": [
    {{"name": "Kai", "kind": "person", "aliases": [], "confidence": 1.0}},
    {{"name": "Harbin", "kind": "place", "aliases": [], "confidence": 0.95}},
    {{"name": "Imperial Academy", "kind": "organization", "aliases": [], "confidence": 0.9}},
    {{"name": "Jade Seal", "kind": "artifact", "aliases": [], "confidence": 0.9}}
  ]
}}
```

## Example B — scene-relevance filter

TEXT:
"Anya sat in the parlour at Whitestone Cottage, looking out across the
moor toward Tavistock. She thought of her late uncle Reginald, who had
served in the Royal Engineers and died in Singapore years ago. The
present trouble, however, came from her stepfather Caldwell, who had
returned from his estates in Berkshire and Hampshire that morning in a
foul humour. He paced the drawing-room. Outside, the village idiot
Old Tom hooted at the gate."
KNOWN_ENTITIES: []

Output:
```json
{{
  "entities": [
    {{"name": "Anya", "kind": "person", "aliases": [], "confidence": 1.0}},
    {{"name": "Whitestone Cottage", "kind": "place", "aliases": [], "confidence": 0.95}},
    {{"name": "Caldwell", "kind": "person", "aliases": [], "confidence": 0.95}},
    {{"name": "Old Tom", "kind": "person", "aliases": [], "confidence": 0.85}}
  ]
}}
```

Notice what is OMITTED and WHY:
- **Tavistock** — geographic aside (where the moor points to), not a
  scene setting Anya is in.
- **Reginald**, **Royal Engineers**, **Singapore** — backstory about
  a dead uncle, not actors in this chapter.
- **Berkshire**, **Hampshire** — decorative places (estate locations
  Caldwell returned from), not scene settings here.

Caldwell IS extracted because he is present in the scene (paces the
drawing-room) and is the subject of the chapter's concerns. Old Tom
IS extracted because he is physically present at the gate.

Now extract from TEXT. Return only the JSON object.
