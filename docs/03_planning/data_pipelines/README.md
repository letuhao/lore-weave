# Data Pipelines

Pipeline designs for LoreWeave's data processing layer. Each pipeline is a separate concern with clear inputs/outputs.

## Pipeline Index

| Pipeline | Status | Doc |
|----------|--------|-----|
| **Translation V2** | Design | [TRANSLATION_PIPELINE_V2.md](TRANSLATION_PIPELINE_V2.md) |
| **Glossary Extraction** | Design | [GLOSSARY_EXTRACTION_PIPELINE.md](GLOSSARY_EXTRACTION_PIPELINE.md) |
| **Metadata Extraction** (timeline, facts, relations, scenes) | Future | — |
| **Quality Validation** (post-hoc translation QA) | Future | — |

## Reference

| Doc | Purpose |
|-----|---------|
| [TRANSLATION_PIPELINE_COMPARISON.md](TRANSLATION_PIPELINE_COMPARISON.md) | MVTN (old monolith) vs LoreWeave (current) analysis |

## Principles

1. **Single responsibility** — each pipeline does one thing
2. **Read from services, write to services** — no direct DB coupling between pipelines
3. **Context-engineered prompts** — token budgets, glossary injection, validation
4. **Fail loud** — no silent fallbacks, log everything, mark partial results
5. **Incremental** — pipelines can run independently, in any order, re-run safely
