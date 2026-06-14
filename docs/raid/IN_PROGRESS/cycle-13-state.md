
## DESIGN (recorded)
DPS1 knowledge BE: migrate pinned_entity_ids JSONB; StartJobRequest.pinned_glossary_entity_ids; thread inline INSERT + repo create + _SELECT_COLS + ExtractionJob(Create); orchestrator pinned_names prepend at both _run_pipeline call sites; cost line (_TOKENS_PER_PINNED_ENTITY=50, EstimateRequest.pinned_count, EstimateResponse.estimated_pinned_tokens folded into estimated_tokens, num_windows≈chapters).
DPS2 worker-ai: GlossaryClient.fetch_entities_by_ids (POST entities/by-ids, reuse X-Internal-Token); JobRow.pinned_entity_ids + SQL; process_job fetch-once after book_id; thread pinned_names into _start_decoupled_chunk + _extract_and_persist (replace known_entities=[]).
DPS3 glossary BE: GET /internal/books/{book_id}/entities/stats GROUP-BY chapter_entity_links; {entity_id,name,kind,mention_count,first/last_chapter_index,coverage_pct}; chapter_count via fetchBookChapters.
DPS4 FE: Step-2 dual-list + auto-pin banner (stats endpoint) + per-window budget; POST pinned_glossary_entity_ids.

## REVIEW(design): no OUT items — no C12 target-gating/shell change (only fill Step-2 placeholder), name-prefix injection only (no separate prompt block), reuse X-Internal-Token (no new secret), no C14. CLEAR.
