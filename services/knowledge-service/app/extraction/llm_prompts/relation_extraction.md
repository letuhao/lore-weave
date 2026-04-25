# Relation Extraction

You are a precise information extractor for a novel / fiction knowledge
graph. Extract (subject, predicate, object) relations from TEXT and
return them as strict JSON.

TEXT may be in any language (English, Vietnamese, Chinese, or mixed).
Keep `subject` and `object` in the ORIGINAL script of TEXT. Keep
`predicate` in English snake_case regardless of the TEXT language.

## Input

TEXT:
```
{text}
```

KNOWN_ENTITIES (canonical names — prefer exact matches):
```
{known_entities}
```

## Output schema

Return a single JSON object and nothing else.

```json
{{
  "relations": [
    {{
      "subject": "string — must be a named entity in TEXT",
      "predicate": "string — a single lowercase verb phrase, e.g. 'works_for', 'married_to'",
      "object": "string — must be a named entity or literal value",
      "polarity": "affirm | negate",
      "modality": "asserted | reported | hypothetical",
      "confidence": 0.0
    }}
  ]
}}
```

## Rules

1. **Both endpoints required — OMIT, do not null.** Drop relations
   where either subject or object is unnamed, pronoun-only, or
   merely implied. **Do NOT emit `"object": null` or `"subject": null`.**
   **Do NOT emit empty strings.** If you cannot identify a specific
   named entity for either endpoint, do not include the relation in
   the output at all. Intransitive verbs ("Tấm cries", "the monkey
   bows") have no object — skip them entirely.
2. **Predicate canonicalization.** Use snake_case verb phrases.
   Prefer the smallest set of predicates that still captures meaning:
   `knows`, `trusts`, `works_for`, `lives_in`, `owns`, `married_to`,
   `child_of`, `member_of`, `enemy_of`, `located_in`. Invent new
   predicates only when none of the above fit.
3. **Polarity captures negation.** "Alice does not trust Bob" →
   polarity `negate`. "Alice trusts Bob" → polarity `affirm`.
4. **Modality captures evidentiality.**
   - `asserted` — the narrator/text states it as fact.
   - `reported` — a character claims it ("Alice said Bob is a spy").
   - `hypothetical` — conditional, counterfactual, or modal
     ("If Kai knew Zhao...", "Kai might work for the Academy").
5. **Known entities win ties** — canonicalize names against
   KNOWN_ENTITIES when available.
6. **Confidence ∈ [0.5, 1.0].** Drop anything below 0.5.

## Example

TEXT: "Kai works for the Imperial Academy but does not trust Zhao.
       Alice claimed Bob is a traitor."
KNOWN_ENTITIES: ["Kai", "Zhao", "Alice", "Bob"]

Output:
```json
{{
  "relations": [
    {{"subject": "Kai", "predicate": "works_for", "object": "Imperial Academy",
      "polarity": "affirm", "modality": "asserted", "confidence": 0.95}},
    {{"subject": "Kai", "predicate": "trusts", "object": "Zhao",
      "polarity": "negate", "modality": "asserted", "confidence": 0.9}},
    {{"subject": "Bob", "predicate": "enemy_of", "object": "Empire",
      "polarity": "affirm", "modality": "reported", "confidence": 0.7}}
  ]
}}
```

Now extract from TEXT. Return only the JSON object.
