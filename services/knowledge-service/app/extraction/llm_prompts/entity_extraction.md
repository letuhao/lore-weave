# Entity Extraction

You are a precise information extractor for a novel / fiction knowledge
graph. Extract named entities from the TEXT below and return them as
strict JSON conforming to the schema.

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

## Example

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

Now extract from TEXT. Return only the JSON object.
