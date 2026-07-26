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

**Fixes landed this run (hard-block / wedge class):**
- **#5 → FIXED** `516d33eba` — frontend tools now feed the shared repeated-failure breaker + get de-advertised at the same cap (D-FE-TOOL-LOOP). 4 regression tests.
- **#3 → FIXED** (D-RAIL-NEXT-STEP-EXEMPT) — the rail's NEXT actionable step tools are budget-exempt in the surface seed; the driven step is always on the wire. Note: the RESUME path still seeds from `susp.pinned_step_tools` without done/next info (pre-existing, lower risk) — tracked here, not fixed.

---

## Run log (Track A — the book)

*(chapter-by-chapter status appended as the run progresses)*
