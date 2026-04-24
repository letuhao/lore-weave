<!-- CHUNK-META
source: 05_LLM_SAFETY_LAYER.ARCHIVED.md
chunk: 01_intent_classifier.md
byte_range: 1418-2703
sha256: b4f10cdb7c28db66d6e46d692995685de3b7f0693be2026b877830aa254be7f6
generated_by: scripts/chunk_doc.py
-->

## 2. Three-intent classifier (A5-D1)

Every player input is classified into exactly one of three intents before any LLM call:

| Intent | Example | Handler | LLM role |
|---|---|---|---|
| **Command** | `/take map`, `/attack guard`, `/hide`, `/move north` | `world-service` deterministic dispatch | Narrate POST-commit |
| **Fact question** | "Where is the treasure?", "Who killed the king?", "Does Elena love me?" | World Oracle lookup | Wrap fixed answer in persona |
| **Free narrative** | "I walk toward Elena and smile", "*looks uneasy*", "I've been thinking about the forest..." | LLM creative generation | Full creative output (persona + canon retrieval constrained) |

### Classifier implementation

- Commands: regex match `^/\w+` → command intent (unambiguous)
- Fact question: small NLI model or rule-based heuristic (question mark + known-entity NER + fact-pattern lexicon)
- Default / unmatched: free narrative

Classifier is cheap (local model or rules). Misclassification cost:
- Command as narrative: player intent lost, retry UX
- Fact question as narrative: non-deterministic answer, canon drift risk (audit-logged `oracle.classifier_miss`, feeds V1 tuning)
- Narrative as fact: false positive Oracle lookup, retry with narrative path

---

