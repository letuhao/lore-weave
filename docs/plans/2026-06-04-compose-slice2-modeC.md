# Plan — Compose Slice 2 (mode C, paste-context) · 2026-06-04

Spec: [docs/specs/2026-06-03-enrichment-compose.md](../specs/2026-06-03-enrichment-compose.md) §2.3 (context branch), §4 (①②③④), §5 (slice 2 row). Branch `lore-enrichment/foundation`. Type: **L FS** (BE + contract + FE + i18n×4 + tests). Each slice = own VERIFY+POST-REVIEW+COMMIT.

## Goal
`input_source="context"`: the author pastes reference text → it is ingested as a grounding corpus (the C2 `ingest_corpus` seam) → a normal retrieval/recook job runs on the chosen target, grounded on that corpus (the C2 grounding composer picks it up by `project_id`). **Zero worker/strategy change** (spec §1).

## Acceptance (spec §5 slice 2)
- live: pasted text → corpus → recook/retrieval **proposal grounded on it**; `copyrighted` assertion **refused**.

## BE — `app/api/compose.py` (only file)
1. `ComposeBody` += `context_text: str | None`, `context_license: str | None`.
2. `_SUPPORTED_SOURCES` += `"context"`; drop from `_FUTURE_SOURCES`.
3. New `if source == "context"` branch (after draft, before gap):
   - validate: non-empty `context_text`; `len ≤ _MAX_DRAFT_CHARS` (reuse cap → 413 "use mode F"); `target` present; `embedding_model_ref` present (the paste is embedded) → 400 each.
   - **license default-deny:** map FE `context_license` → store license: `public_domain→public_domain`, `licensed→licensed`, `owned→licensed` (author-owned ⇒ re-cook-admissible, mirrors `/ground`). Anything else incl. `copyrighted`/unknown → **403** (defensible: user must own / PD / license it).
   - technique = `Technique(body.technique or RETRIEVAL)`; reject `compose_draft` (→ use draft) → 400.
   - **ingest synchronously** via `_ingest_context` (build `KnowledgeClient` embed seam like `/ground` → `store.ingest_corpus`); corpus `name=f"compose-context:{book_id}:{sha256(text)[:12]}"`, `kind="other"`, mapped license, `project_id=path param`. Idempotent (same paste → same corpus). 502/503 on embed failure (mirror `/ground`).
   - target → `_target_dict`; existing → best-effort `_resolve_present_dimensions` (spec §2.2: present from coverage; fill missing grounded on the new corpus); new → `[]`.
   - `_create_and_enqueue(technique, entity_kind=target.entity_kind, targets=[target], extra_request={"context_corpus_ids":[id], "context_license":store_license})`.
4. `_ingest_context(pool, principal, project_id, body, text, store_license) -> list[str]` helper (returns corpus_ids).

No migration (reuse `enrichment_job` + JSONB request; `context_corpus_ids` already named in spec §2.7 as audit). No worker change.

## Contract — `openapi.yaml`
Add `context_text` (maxLength 50000) + `context_license` (enum public_domain|licensed|owned|copyrighted) to the `/compose` request schema.

## FE — `features/enrichment/`
- `components/compose/ComposeContextForm.tsx` (new): paste `<textarea>` + license `<select>` (public_domain|licensed|owned|copyrighted) + a "you are responsible / NOT legal advice" note. View-only (state in ComposePanel).
- `ModeSelector.tsx`: `context` status `'soon'` → `'active'`.
- `ComposePanel.tsx`: context state (`contextText`, `contextLicense`); render `ComposeContextForm` + `ComposeTarget` + `ComposeConfig` when `mode==='context'`; `canRun` for context (text + target + genModel + **embedModel required** + license≠copyrighted + not composing); `run()` builds the context body (`input_source:'context'`, `context_text`, `context_license`, `embedding_model_ref`, `technique` default retrieval).
- `types.ts`: `ComposeBody` += `context_text?`, `context_license?: License`.
- `api.ts`: no change (compose() is generic).
- i18n ×4: `compose.context.*` (label/placeholder/license labels/responsibility) + enable existing `compose.mode.context`.

## Tests
- **BE pytest** (`tests/test_compose_api.py` or similar): context 202 + request shape (ingest mocked, technique=retrieval, `context_corpus_ids` persisted); copyrighted → 403; over-cap → 413; missing embed_ref → 400; missing target → 400; compose_draft technique → 400.
- **FE vitest**: `ComposeContextForm` (text/license change), `ComposePanel` context mode (run body = input_source context + license + embed required gates run), `useCompose` already covered.

## Risks
- C12 on the grounded dims — same as retrieval (already covered). Recook license gate honored (mapped license admissible).
- Synchronous ingest in the request path — bounded by the 50 KB cap (large → mode F, slice 3).
- Live: needs embed model (LM-Studio same-owner; eviction risk) + rebuilt service.
