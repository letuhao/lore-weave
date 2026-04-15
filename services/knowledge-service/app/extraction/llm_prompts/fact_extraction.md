# Fact Extraction

You are a precise information extractor for a novel / fiction knowledge
graph. Extract standalone factual claims from TEXT — statements the
narrator or a character asserts about the world, distinct from
relations (which need a typed predicate) and events (which need a
verb of change).

## Input

TEXT:
```
{text}
```

KNOWN_ENTITIES:
```
{known_entities}
```

## Output schema

```json
{{
  "facts": [
    {{
      "content": "string — natural-language fact, one sentence",
      "type": "description | attribute | negation | temporal | causal",
      "subject": "string | null — the primary entity the fact is about",
      "polarity": "affirm | negate",
      "modality": "asserted | reported | hypothetical",
      "confidence": 0.0
    }}
  ]
}}
```

## Rules

1. **Facts are standalone claims.** "The Jade Seal is priceless" is
   a fact. "Kai carries the Jade Seal" is a relation, not a fact.
2. **Subject is optional** but extract it when the fact is clearly
   about one entity. Universal claims ("The Empire was vast") may
   have `subject: null`.
3. **Negation facts are first-class.** "Kai did not trust Zhao" →
   type `negation`, polarity `negate`. Capture these explicitly
   because they encode what the text DOES NOT say, which downstream
   L2 retrieval uses to prevent hallucinated reconciliation.
4. **Temporal facts** capture time anchors: "The war ended in the
   third year of Emperor Wen". Use type `temporal`.
5. **Causal facts** capture cause/effect: "Because Zhao fell, the
   rebels took Iron Gate". Use type `causal`.
6. **Reported facts** go in the list with `modality: reported` —
   the `content` field must make the hedge explicit, e.g. "Alice
   claimed the Jade Seal was a fake".
7. **Confidence ∈ [0.5, 1.0].** Drop below 0.5.

## Example

TEXT: "The Jade Seal was priceless. Kai did not trust Zhao. Alice
       insisted the Seal was a fake. When the war ended in the third
       year of Emperor Wen, the Iron Gate fell because Zhao was dead."
KNOWN_ENTITIES: ["Jade Seal", "Kai", "Zhao", "Alice", "Emperor Wen", "Iron Gate"]

Output:
```json
{{
  "facts": [
    {{
      "content": "The Jade Seal was priceless.",
      "type": "description", "subject": "Jade Seal",
      "polarity": "affirm", "modality": "asserted", "confidence": 0.95
    }},
    {{
      "content": "Kai did not trust Zhao.",
      "type": "negation", "subject": "Kai",
      "polarity": "negate", "modality": "asserted", "confidence": 0.9
    }},
    {{
      "content": "Alice claimed the Jade Seal was a fake.",
      "type": "description", "subject": "Jade Seal",
      "polarity": "affirm", "modality": "reported", "confidence": 0.7
    }},
    {{
      "content": "The war ended in the third year of Emperor Wen.",
      "type": "temporal", "subject": null,
      "polarity": "affirm", "modality": "asserted", "confidence": 0.9
    }},
    {{
      "content": "The Iron Gate fell because Zhao was dead.",
      "type": "causal", "subject": "Iron Gate",
      "polarity": "affirm", "modality": "asserted", "confidence": 0.85
    }}
  ]
}}
```

Now extract from TEXT. Return only the JSON object.
