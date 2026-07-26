# Mị Đế author-dogfood run — 2026-07-26

**What this is:** an end-to-end "real author" simulation. The agent plays a professional writer
using the writing studio through the **frontend only** (Playwright, test account, local gemma)
to write a real book (Mị Đế — tu chân khoa học, Vietnamese prose). Seed: `D:\Works\novels\mi_de\Mi_De_Story_Seed.md` (baseline only; expanded with the author's own ideas in-run).

**Milestone scope (agreed):** book setup + 3 chapters through the full loop
(plan → review/edit plan → draft → evaluate → atom-edit polish → publish → canon update).

**Ground rules (agreed with PO):**
- Vietnamese prose; local gemma ($0). One thought per chat message — no spec-dumps.
- Frontend-only for authoring. DB/logs are **observer-only** evidence.
- **Log, don't fix** mid-run — a bug becomes a findings row, not a mid-run patch,
  unless it hard-blocks the loop.
- Read every chapter in full before publishing; judge_prose is a second opinion, not the verdict.

## Persona quality rubric (5 hats per chapter)
Continuity editor · Line editor · Character coach · Genre reader (tu chân khoa học rigor) · Architect (seed ledger advanced?)

## Seed ledger (long-range payoffs the platform must carry)
| Seed | Planted | Must pay off |
|---|---|---|
| Thanh Tâm Ấn on Huyết Vô Thường | (not yet) | Huyết Chủ recognition, vạn năm sau |
| Chân Linh bất biến (soul-layer stack) | (not yet) | rebirth identity continuity |
| Tô Thanh Dao → Lâm Trạch (hidden) | (not yet) | Arc-1 death-scene reveal |

---

## Findings log (Track B — the product payoff)

| # | Phase | Severity | What a real user experienced | Evidence |
|---|---|---|---|---|
| 1 | onboarding | MED (UX) | "Start something new → Write" drops the user on the plain /books list — no creation flow, no guidance. Newcomer dead-end; had to find "New Book" myself. | /onboarding/new → click Write → lands /books |
| 2 | first chat turn | MED | Assistant's opening reply persisted **duplicated verbatim** (same 6 paragraphs twice in one bubble). Model re-emitted pre-tool-call text after the tool round and the stream buffer kept both. | terminal-persist msg 7ae648ef… saved at 943 chars then 1884 chars (exactly doubled) |
| 3 | first chat turn | MED | Rail advertises steps whose tools were budget-dropped — agent told to do a step it cannot see the tool for. | `WARNING: pinned rail step tools dropped by the token budget: kg_project_entities_to_nodes, plan_propose_spec` |
| 4 | first chat turn | INFO (breaker OK) | `glossary_propose_entities` failed 2× same error → breaker short-circuited + de-advertised. Guard worked for the backend tool. | chat-service log, session 019f9f2e |
| 5 | first chat turn | **HIGH** | **Endless tool loop**: ~205 calls of `glossary_propose_entity_edit` in ONE turn, identical malformed args `{"base_version":"1","book_id":",changes:[{field_label:"}`. Neither the repeated-failure breaker nor the per-turn tool budget stopped it — **frontend tools bypass both guards**. User watched the agent spin for ~4 min and had to hit Stop. | LM Studio log 2026-07-26.16.log: 410 packets output_index→118+; breaker log shows only the backend sibling tripped |
| 6 | chat UI | LOW (UX) | Esc is globally bound to "Stop generating", so closing any open menu with Esc during generation risks aborting the turn. | mode-menu open during gen; hint "Stop generating (Esc)" |
| 7 | after restart | MED (UX) | The interrupted assistant reply vanished from the visible transcript (it IS in the DB as `interrupted`) — user loses what the co-writer had said. | msg 7ae648ef persisted 1884 chars; UI shows no bubble after reload |
| 8 | KG edge | MED | Model swallowed a FAILED approved write: `kg_propose_edge` errored ("endpoints not yet graph nodes") but the reply said everything was set up. User believes a relation exists that doesn't. | tool_calls JSONB: ok=false + the cheery final reply |
| 9 | KG edge | INFO (good) | The edge error itself is excellent: names the repair tool + the order. Tool-side contract is right; the model + surface let it down. | error text in row 8 |

| 10 | every multi-round turn | MED→**FIXED** | Reply bubble repeats the same content once per tool round (observed 4×) — gemma re-emits its full prior text verbatim each continuation pass and the stream concatenates passes. | persist 943→1884 (2×), 771→1542; 4-copy bubble at 11:42 PM |
| 11 | breaker verify | INFO (good) | Post-fix live turn: the same entity_edit misuse stopped at **2 calls** (vs 205), model apologised honestly + formed the correct 4-step plan. Fix #5 verified by effect. | tool_calls: 2×✗ then honest text |

| 12 | cast setup | MED | Cross-turn misuse persistence: each NEW turn the model reaches for `entity_edit`-to-create again — the breaker + de-advertise are per-turn, and its own history keeps re-teaching the mistake. | 3 consecutive turns, same wrong tool first |
| 13 | ontology | MED (UX) | Guided setup adopted only 3 real kinds (character/location/item) — no faction/organization for a xianxia book; "Lâm gia" had no valid kind until I adopted more via Ontology → Adopt more (works well). | New-entity dialog showed 4 kinds |
| 14 | cast setup | **HIGH (model)** | Read-then-act hallucination: model `tool_load`ed `glossary_propose_entities` then ANNOUNCED all 3 characters proposed — never called the tool. DB: nothing created. | msg f632d173: tool_calls=[tool_load✓ only] + "Đã xong!" |
| 15 | cast setup | **HIGH→FIXED** | Frontend tools never receive the session's context-ids (the S02 injector sits below the FE branch) — the model must transcribe book_id itself, invents one ("ID giả định"), fails validation every time. | msg 854e5a33: 2×✗ "book_id must be a real UUID" |
| 16 | echo guard v1 | MED→**FIXED** | First echo-guard cut missed every real echo: gemma opens the re-echo with "\n\n", the exact-prefix match diverged on char 1. Now whitespace-tolerant at the seams. | msg 854e5a33 content: copy1+"\n\n"+copy2 |

| 17 | review inbox | MED (UX) | AI-suggestions card shows only name+kind ("appears in 0 chapters") — the 7 proposed attributes (gender, role, personality, description…) are invisible, so the human approves blind. | Lâm Uyên card vs DB attributes |
| 18 | activated state | **HIGH→FIXED** | **The degradation loop's true root**: `merge_activated_tools` deduped by FIRST occurrence, so a re-`tool_load`ed tool kept its oldest LRU slot and was evicted first by the budget. Model re-loaded `glossary_propose_entities` every turn; it was gone by the next; the always-visible edit tool absorbed the intent → the "placeholder_id" loop. | advertised sets: 17→15 tools, propose_entities missing the turn after its tool_load |

**Fixes landed this run (hard-block / wedge class):**
- **#15 → FIXED** (D-FE-TOOL-CONTEXT-IDS) — frontend branch now runs `_inject_context_ids` (fill-blank + replace-malformed + studio override) before validation.
- **#16 → FIXED** (D-PASS-TEXT-REECHO v2) — lstripped probe vs stripped turn text.
- **#18 → FIXED** (D-ACTIVATED-LRU-REFRESH) — re-activation moves the name to the recency end; the just-requested tool now survives eviction.

| 19 | activated state | **HIGH→FIXED** | **The deeper layer under #18**: this session is AUTO mode (no pins), and `tool_load` activation was persisted only `if curated` — every load evaporated at turn end BY DESIGN; auto seed re-advertised only hot-seed ∪ (activated ∩ workflow steps). The model could never keep the create tool visible no matter what it did. Answer to "wrong instruction or never seen?": **never seen** — instructions are good (model even tool_loads the right name); the edit tool is frontend-core (always visible) so the create intent kept landing there. | session row: enabled_tools={} activated_tools={}; advertised sets lack propose_entities the turn after its tool_load✓ |

- **#19 → FIXED** (D-TOOL-LOAD-PERSISTS) — tool_load persists ungated (the workflow_load precedent, same rationale); auto-mode seed re-advertises a bounded recency tail (`AUTO_ACTIVATED_TAIL=6`) so the freshly-loaded tool survives the turn boundary while stale accumulations stay bounded out.
- **#10 → FIXED** (D-PASS-TEXT-REECHO) — continuation-pass opening tokens held while they verbatim-prefix the turn's streamed text; full echo swallowed, divergence flushed unchanged (incl. straddling delta). 3 regression tests.
- **#5 → FIXED** `516d33eba` — frontend tools now feed the shared repeated-failure breaker + get de-advertised at the same cap (D-FE-TOOL-LOOP). 4 regression tests.
- **#3 → FIXED** (D-RAIL-NEXT-STEP-EXEMPT) — the rail's NEXT actionable step tools are budget-exempt in the surface seed; the driven step is always on the wire. Note: the RESUME path still seeds from `susp.pinned_step_tools` without done/next info (pre-existing, lower risk) — tracked here, not fixed.

---

## Run log (Track A — the book)

*(chapter-by-chapter status appended as the run progresses)*
