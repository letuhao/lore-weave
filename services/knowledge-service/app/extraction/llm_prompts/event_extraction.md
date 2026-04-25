# Event Extraction

You are a precise information extractor for a novel / fiction knowledge
graph. Extract narrative events from TEXT and return them as strict
JSON. Events are time-indexed happenings with participants — distinct
from static relations.

TEXT may be in any language (English, Vietnamese, Chinese, or mixed).
Keep `name`, `participants`, `location`, `time_cue`, and `summary` in
the ORIGINAL script of TEXT. Keep `kind` values in English.

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
      "event_date": "string | null — ISO date when TEXT contains an explicit calendar date (truncated allowed: 'YYYY' / 'YYYY-MM' / 'YYYY-MM-DD'). Null otherwise.",
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
5. **`event_date` is optional and DISTINCT from `time_cue`.** Extract
   ONLY when TEXT contains an explicit calendar date or year that
   maps cleanly to ISO format:
   - "summer 1880"     → `"1880-06"` (year-month, season → month)
   - "June 15, 1880"   → `"1880-06-15"` (full ISO)
   - "the year was 1880" → `"1880"` (year-only)
   **Do NOT invent.** Vague hints ("the next morning", "in his
   youth", "long ago", "later that day") → leave null; those go
   in `time_cue`. Fictional eras ("TA 3019", "Year of the Dragon")
   → leave null; those also go in `time_cue` only.
6. **Reported / hypothetical events go in `events` too** but the
   `summary` must make the evidentiality explicit, e.g. "Alice
   claimed Bob betrayed the Empire".
7. **Kind fallback.** Use "other" if none fit; do not invent kinds.
8. **Confidence ∈ [0.5, 1.0].** Drop below 0.5.
9. **No duplicates.** Fold repeated mentions of the same event into
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
      "event_date": null,
      "summary": "Kai departs from Harbin carrying the Jade Seal.",
      "confidence": 0.95
    }},
    {{
      "name": "Battle at Iron Gate",
      "kind": "battle",
      "participants": ["Zhao"],
      "location": "Iron Gate",
      "time_cue": "later that day",
      "event_date": null,
      "summary": "Zhao fights rebels at the Iron Gate and dies.",
      "confidence": 0.9
    }}
  ]
}}
```

Now extract from TEXT. Return only the JSON object.
