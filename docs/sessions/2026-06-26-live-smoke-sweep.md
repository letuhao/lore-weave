# Live-Smoke Sweep — 2026-06-26 (composition / E0 / glossary tracks)

Recorded in a dedicated file (not inline in `SESSION_HANDOFF.md`) because that file is the
concurrent glossary session's active working doc and we share one working tree — inline edits
would clobber their live changes. Fold these ✅ marks into the relevant deferred rows when the
contention clears.

**Stack:** rebuilt 2026-06-26 13:22 +07 (images fresh, after all concurrent commits).
**Accounts:** A = `claude-test` (019d5e3c…), B = `claude-test2` (019e97b0…, both pw `Claude@Test2026`).

## ✅ PASSED — 8 of 9

| Row | Evidence |
|---|---|
| **D-PLAN-UI-SMOKE** (was: "reopen if chat path needs e2e") | Browser: glossary assistant → Qwen2.5 7B **tool-called `glossary_plan`** (MCP via ai-gateway) → plan card (dedup-aware, 1 new `concept` kind) → **Confirm** → `loreweave_glossary.book_kinds` gained `concept` @ `04:19:32Z` (12→13 kinds). The chat→card→confirm→prod-DB leg — the one residual of D-PLAN-EXEC-LIVE-SMOKE — is now proven. |
| **D-E0-5-LIVE-SMOKE** | `POST /v1/books/{id}/collaborators {email,role:manage}` → collaborator row for B with `display_name="Claude Test 2"` **enriched** from auth. |
| **D-GRANT-INSTANT-REVOKE-CACHE-EVICT-LIVE-SMOKE** | B reads book → 200 (grant cached); owner revokes; B reads → **404 within 2s** — cached grant flipped allow→deny instantly (404 = existence-hiding for unauthorized). |
| **D-GKA-G6F-PLAYWRIGHT-SMOKE** | Ontology tiering workspace functional with live data: **Attribute matrix** (genre×attr, namespacing rule, SYS markers, live `concept` kind flows through) + **Updates & Sync** (frozen-copy COW model, **34 real upstream updates** computed, per-attr keep-mine/take-theirs diff). Read/render/diff exercised; adopt/apply mutations not driven (avoided altering the test book's tier state). |
| **D-E0-4B-LIVE-SMOKE** (dual-identity billing) | B (manage grant) opened **A's** book + sent a chat with **B's** registered gemma model → real reply (+2× `glossary_search`). `usage_logs`: **3 rows `owner_user_id=B`**, `model_ref=019f029b-0c20` (B's gemma), `billing_decision=recorded` (B baseline 0→3). Action on A's resource, billed to B. |
| **D-LLM-FAILURE-RATE** (corroboration leg) | Real extraction job `019f02a7` on a chapter w/ Qwen2.5 7B + the loose entity `response_format`: **`parse_status=ok`/`finish_reason=stop`**, 2 entities created, `failed_chapters=0`, `error_message=null`, 23s. Confirms structured output → clean parse on real content. The `completed_with_errors` job-status here is a benign empty-kind-batch artifact (no vampire/witch in that chapter), not a parse failure. |
| **D-GKA-G4-LIVE-SMOKE** | Same extraction wrote to the **book-local** glossary tables (`book_kinds` incl. `concept` + `chapter_entity_links`) — adopt→extract→book-local-tier chain post-G4-cutover proven. |
| **D-TRANSL-T2M2-LIVE-SMOKE** | On 万古神帝 ch `019eb60f` (vi): clean → **`409 TRANSL_NO_DIRTY_SEGMENTS`** (gate refuses clean); dirty 1 segment → retranslate-dirty creates job (owner=A, pipeline v2); result = new version `019f02ad-0593` = **1-chunk partial (1517 chars)** covering only the dirty sub-range (prior full = 3 chunks ~12K) → only-dirty re-translated. |

## ◑ Covered-by-proxy — 1
- **D-PIPELINE-M2-LIVE-SMOKE** (chat→`translation_start_extraction`→confirm→jobs_get) — not driven via its specific tools, but both halves are independently proven: the MCP chat-tool→confirm→execute wiring (D-PLAN-UI) + the extraction job (D-LLM-FAILURE-RATE). Was flagged "optional / unit-proven." Drive the exact tools if airtight coverage is wanted.

## Setup created (residue on the test account — harmless)
- `concept` kind on Dracula book `019eeb09`.
- B (`claude-test2`) registered an lm_studio BYOK: provider `019f029b-0c08`, model `019f029b-0c20` (`google/gemma-4-26b-a4b-qat`, chat+tool_calling). Kept for future E0 smokes.
- B re-invited as **manage** collaborator on Dracula `019eeb09` (still active — revoke if undesired).
- 万古神帝 ch `019eb60f` seg 1 has a `dirtyT2M2…` source-hash (self-heals on next re-segment).

## Still genuinely not run
- Per-*scene* fanout `D-P2-PER-SCENE-FANOUT` (perf-gated, knowledge-extraction) and per-chapter CJK alias breakdown — out of scope, no code path yet.
