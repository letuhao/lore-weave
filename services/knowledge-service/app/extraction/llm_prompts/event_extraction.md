# Event Extraction

You are a precise information extractor for a novel / fiction knowledge
graph. Extract narrative events from TEXT and return them as strict
JSON. Events are time-indexed happenings with participants — distinct
from static relations.

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
  "events": [
    {{
      "name": "string — short imperative phrase, e.g. 'Kai leaves Harbin'",
      "kind": "action | dialogue | battle | travel | discovery | death | birth | other",
      "participants": ["string — entity names"],
      "location": "string | null",
      "time_cue": "string | null — any temporal anchor from TEXT (e.g. 'at dawn', 'next spring')",
      "summary": "string — one-sentence neutral description",
      "confidence": 0.0
    }}
  ]
}}
```

## Rules

1. **Events must have a verb of change.** "Kai was tall" is a state,
   not an event. "Kai grew taller" is an event.
2. **Participants must be named.** Drop events where no named entity
   is involved.
3. **Location is optional** but extract it when TEXT provides one.
4. **Time cue is optional.** Capture whatever temporal phrase TEXT
   uses; do not invent a date.
5. **Reported / hypothetical events go in `events` too** but the
   `summary` must make the evidentiality explicit, e.g. "Alice
   claimed Bob betrayed the Empire".
6. **Kind fallback.** Use "other" if none fit; do not invent kinds.
7. **Confidence ∈ [0.5, 1.0].** Drop below 0.5.
8. **No duplicates.** Fold repeated mentions of the same event into
   one entry even if TEXT restates it.

## Example

TEXT: "At dawn, Kai left Harbin carrying the Jade Seal. Later that
       day, Zhao battled the rebels at the Iron Gate and fell."
KNOWN_ENTITIES: ["Kai", "Harbin", "Zhao", "Iron Gate"]

Output:
```json
{{
  "events": [
    {{
      "name": "Kai leaves Harbin",
      "kind": "travel",
      "participants": ["Kai"],
      "location": "Harbin",
      "time_cue": "at dawn",
      "summary": "Kai departs from Harbin carrying the Jade Seal.",
      "confidence": 0.95
    }},
    {{
      "name": "Battle at Iron Gate",
      "kind": "battle",
      "participants": ["Zhao"],
      "location": "Iron Gate",
      "time_cue": "later that day",
      "summary": "Zhao fights rebels at the Iron Gate and dies.",
      "confidence": 0.9
    }}
  ]
}}
```

Now extract from TEXT. Return only the JSON object.
