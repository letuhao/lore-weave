# Per-language aliases (D-GLOSSARY-PERLANG-ALIASES / S6) — full-vertical plan

> **Decision (locked):** Option (a) — a per-language alias set is a **translation of the entity's `aliases` attribute value** in `attribute_translations` (value = a JSON array of target-language alias strings). No new table. Rationale + evidence: the aliases attr is structurally identical to scalar attrs (`field_type='tags'`, JSON-string in `entity_attribute_values.original_value`); `attribute_translations` already has `UNIQUE(attr_value_id, language_code)` → exactly one alias-set per language. See the S6 analysis (this session).
> **Scope:** FULL vertical (user-approved): write tool → extraction resolver → knowledge `cached_aliases` → FE renderer.
> **Build order:** each part is a risk boundary → checkpoint/commit when green.

---

## Part 1 — BE write path (glossary-service) [foundation]
**`glossary_propose_aliases`** MCP tool (class-W, Edit; sibling to M4's `glossary_propose_translation`).
- Input: `book_id`, `language_code`, `items: [{entity_id, aliases: []string}]`.
- Per item: resolve the entity-in-book → **resolve-or-create** the entity's `aliases` EAV row (a translation needs an `attr_value_id`; many entities have no aliases row → INSERT an empty `'[]'` source-language row first) → upsert a DRAFT translation whose `value` is `json.Marshal(aliases)` (a JSON array string), **never overwriting `verified`** (reuse `upsertDraftTranslation`).
- Cores: `resolveOrCreateEntityAliasesValue(ctx, entityID, kindID) (attrValueID, err)` + reuse `upsertDraftTranslation`.
- Emit `emitTranslationChanged`. Per-entity results. Tests: write, resolve-or-create, verified-protection, bad-JSON guard.

## Part 2 — extraction resolver language-aware (glossary-service) [anti-resurrection payoff]
`findEntityByNameOrAlias` ([extraction_handler.go:809]) today matches an incoming name against the **source-language** aliases array only. Extend it to ALSO scan `attribute_translations` rows for the `aliases` attr (ANY language), unmarshal each JSON array, and match (same normalize + book/kind scope as the source path — no widening of the match scope, only the alias source set).
- Risk: two entities sharing a target-language alias could collide — but identical to the existing source-language risk; keep the same scope. Test: an entity with an EN alias resolves an incoming EN name to it (cross-language anti-resurrection).

## Part 3 — knowledge-service language-aware `cached_aliases` [cross-service contract]
The chat context renders `cached_aliases` source-language-only. Make it language-aware:
- **glossary internal entities endpoint(s)** that knowledge consumes (`/internal/books/{id}/known-entities` and/or `/entities/by-ids`) gain an optional `language` query/body param; when set, `aliases` is composed = source array ∪ the language's translated array (deduped), else source-only (back-compat).
- **knowledge-service** passes the context's display/target language through `glossary_client` → `cached_aliases` carries the right language. Default unset → unchanged.
- Tests: glossary endpoint composes per-language; knowledge passes the language. (Confirm where the context language lives before wiring.)

## Part 4 — FE tags-translation renderer [review/edit surface]
`AttributeField` renders `aliases` as a source-language tags input. Add a per-language alias view/edit (language selector → the language's alias set, draft/verified badge), reusing the translation API. `frontend/src/features/glossary`.
- Verify: `tsc` + vitest; a per-language alias edit round-trips.

---

## Cross-cutting guards
- **Apply-path gating:** the worker `internalApplyTranslations` must not be made to write the aliases attr as a scalar — per-language aliases are written via Part 1's tool only (JSON-array value). No change needed there unless a caller targets aliases.
- **Confidence/translator:** draft / 'assistant' (agent proposal), mirroring M4; human promotes to verified.
- **Tenancy:** Edit grant via `bookToolAuth`; cross-book entities skipped; verified never clobbered.
