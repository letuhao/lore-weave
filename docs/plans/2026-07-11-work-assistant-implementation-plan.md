# Implementation Plan — Work Assistant Mode (beginning to end)

**Date:** 2026-07-11 · **Spec set:** [`docs/specs/2026-07-11-work-assistant-mode/`](../specs/2026-07-11-work-assistant-mode/README.md)
· **Prereq spec:** [`publish-independent-kg-indexing`](../specs/2026-07-11-publish-independent-kg-indexing.md)
· **Findings register:** [`RED-TEAM-2026-07-11`](../specs/2026-07-11-work-assistant-mode/RED-TEAM-2026-07-11.md)

**Size: XL** (multi-service, multi-phase). Each **work-slice (WS)** below is an independently shippable
`/loom` run: CLARIFY(batched) → DESIGN → PLAN → BUILD → VERIFY → REVIEW → **`/review-impl`** → QC →
POST-REVIEW → SESSION → COMMIT.

---

## 0. The rules for every slice (non-negotiable)

| Gate | Rule |
|---|---|
| **`/review-impl` per slice** | Mandatory. This design was **red-teamed into shape** — 18 P0s, three of them reversing my own decisions. Assume the same density of error in the code. Findings are fixed **in the same slice**, not deferred. |
| **Live-smoke ≥2 services** | Unit-green is insufficient — mock-only coverage has hidden cross-service contract bugs 4× in this repo. Every slice touching 2+ services needs a real-stack smoke. |
| **Consumed-by-effect** | Every setting/flag/guard gets a test asserting the **behavior**, not the stored value. A stored-but-unread flag is the bug class this repo has shipped twice. |
| **Fail-closed** | Every privacy/spend toggle defaults **off** and fails closed on resolution error. |
| **No silent success** | A success status with no work done is a **bug**. Every skip logs a **reason** and surfaces it. |
| **Migration discipline** | Explicit backfill (DEFAULT never revisits rows) · `ON CONFLICT` repeats the partial-index predicate · CHECK widen = idempotent DROP-then-ADD · no `CONCURRENTLY` inside the transactional migrator. |

**Definition of done for a slice:** tests green (`-n auto --dist loadgroup`) · live-smoke evidence string ·
`/review-impl` clean or findings fixed · SESSION_HANDOFF updated · committed.

---

## PHASE 0 — Prerequisite: Publish-Independent KG Indexing

**Ships before any assistant code.** Platform-wide: 4 services. Spec is v2 (red-team-corrected).
**Risk: HIGH** — "canon = published" is duplicated in 6+ places; the red team's verdict on v1 was
*"do not build as written."*

| WS | Scope | Services | Gate |
|---|---|---|---|
| **WS-0.1** | **Chapter-scoped cache invalidation.** `ExtractionLeavesRepo.delete_by_chapter`; `handle_chapter_scenes_reparsed` uses it. **Do this FIRST** — it also fixes today's publish path. Without it, every index click wipes the whole book's extraction cache. | knowledge | unit + a test asserting the other 199 chapters' leaves survive |
| **WS-0.2** | **Columns + backfill.** `chapters.kg_indexed_revision_id`, `kg_exclude`; backfill `= published_revision_id WHERE published`. | book | migration test; **sweeper-set-equivalence proof** (no re-parse storm) |
| **WS-0.3** | **All six writers** set the pointer (incl. **worker-infra** ×2). Hygiene test: every `published_revision_id` writer also writes `kg_indexed_revision_id`. | book, **worker-infra** | grep-based hygiene test |
| **WS-0.4** | **The index action** — new MCP tool + REST + `chapter.kg_indexed` event; empty-prose guard; revision reuse when byte-identical; **scenes parse for a draft revision** (net-new). | book | unit + event emitted |
| **WS-0.5** | **Sweeper** — full query re-key (SELECT + JOIN, not just WHERE — else infinite re-parse loop); concurrent guard; ~~unpublish clears the pointer~~ → **unpublish must NOT clear the pointer** (corrected 2026-07-11 during WS-0.2: this row contradicted spec §3.8 + acceptance #9, which require the index request to **survive** an unpublish — retraction is `kg_exclude`'s job, not unpublish's. The spec is the red-team-corrected authority; see RUN-STATE D-R5). | book | sweeper tests: published · draft-indexed · excluded · trashed · **unpublished-still-indexed** |
| **WS-0.6** | **Generalize the publish gate in every reader** — `kg_indexed` filter on `/internal/books/{id}/chapters`; re-point worker-ai rebuild, passage backfill, ingester, cost estimate. | book, knowledge, worker-ai | **live-smoke:** index 5 drafts → rebuild enumerates all 5 |
| **WS-0.7** | **composition-service mirror** — canon-markers contract gains `kg_indexed_revision_id`+`kg_exclude`; re-key `index_stale`. | book, **composition** | **live-smoke:** publish@A + index draft@B → `index_stale` is **false** |
| **WS-0.8** | **knowledge consumer** — `handle_chapter_kg_indexed` (never `chapter.saved`); passage `canon = (rev == published_rev)`; `kg_exclude` retraction reusing the unpublish retract path. | knowledge | **live-smoke:** draft → index → facts in KG; autosave → **zero** jobs |
| **WS-0.9** | **FE** — "Add to knowledge" + an **indexed-state indicator** (the user must be able to see what's in their KG). | frontend | Playwright |

**Phase-0 exit (all must pass):** draft-never-published → indexed → facts in KG · **autosave does NOT
extract** · published flow unchanged · **the other 199 chapters' cache survives** · rebuild enumerates
draft-indexed chapters · composition badge clears · `kg_exclude` retracts · unpublish preserves the index
request. → **`/review-impl`** → commit.

---

## ~~PHASE 0.5~~ — dissolved into Phase 1 (PO-1)

The platform privacy holes ship as **WS-1.2**, not as a separate track.
⚠️ **Accepted risk:** they are **live today**. If Phase 1 slips, **re-raise this** — a security fix should not
be hostage to a feature schedule. See [`DECISIONS-SEALED`](../specs/2026-07-11-work-assistant-mode/DECISIONS-SEALED.md) PO-1.

---

## PHASE 1 — Assistant MVP + diary-lite

**Goal:** a user opens Assistant from the nav, talks all day, entities land in a review inbox, and
"End my day" produces a diary entry they can keep. **No KG facts yet** (P2), **no coaching** (P2), **no voice**.

| WS | Scope | Spec | Risk |
|---|---|---|---|
| **WS-1.0** 🔴 | **Envelope encryption + blind index (PO-2).** Per-user DEK (KEK in KMS; AES-GCM, the `usage_logs` precedent). Encrypts: diary chapter bodies · `chat_messages.content` for assistant sessions · KG `:Fact.fact_text` for the assistant project. **Ships FIRST** — retrofitting encryption after data exists is far more expensive. ⚠️ It **breaks the GIN trigram index** ⇒ `chat_search_sessions` becomes a **blind index** (HMAC-keyed tokens; accepted leak: token frequency). Embeddings stay plaintext = the recorded residual exposure. **Does NOT hide the diary from a running-server operator** — honest disclosure ships alongside. | [`DECISIONS-SEALED`](../specs/2026-07-11-work-assistant-mode/DECISIONS-SEALED.md) PO-2 | **HIGH / M–L** |
| **WS-1.1** | **`books.kind`** — enum + CHECK + `is_bible→lore` backfill + **DB trigger immutability** + all **4** create paths (incl. `createWorldCore` = `'lore'`, same commit as the backfill). | [`03`](../specs/2026-07-11-work-assistant-mode/03-book-kinds-diary-gui.md) | M |
| **WS-1.2** | **Egress guards (D16) + the folded platform holes (PO-1)** — collaborators · sharing PATCH · **wiki ×4** · **public-MCP resource scoping** · **`memory_*` project leak** · **`getBookAccess` oracle** · notifications · **library/catalog hide** · export. Contract: `kind` on `getBookAccess`+`getBookProjection` (gated behind `lvl != GrantNone`). | [`09`](../specs/2026-07-11-work-assistant-mode/09-settings-consent-privacy.md) | **HIGH** |
| **WS-1.3** | **Schema** — `chapters.{entry_date, journal_kind, diary_kept_at}` + partial unique · `knowledge_projects.{is_assistant}` + one-per-user · **derived fail-closed** extraction gate · `user_chat_ai_prefs.assistant` (+ session override; **widen the category whitelist AND the Pydantic model together**) · **timezone** in auth `user_preferences` · **`chat_messages.local_date`** (write-time) · pg_trgm (**outside the DDL string**, no CONCURRENTLY). | [`01`](../specs/2026-07-11-work-assistant-mode/01-data-architecture.md) | M |
| **WS-1.4** | **Provisioning** — BFF fan-out with the user's JWT; idempotency keys; **extraction bootstrap** (else the drain silently no-ops); tz confirm; **self entity**; consent never side-effect-enabled; **`provision_status`** for partial failure. | [`02`](../specs/2026-07-11-work-assistant-mode/02-assistant-mode-session.md) | M |
| **WS-1.5** | **Work ontology + `flavorWorkCapture`** — System-tier seed as a **new ledger entry**; flavor resolved server-side from `kind`; **Minh-vs-Minh disambiguation item**; no `preference` facts about third parties; special-category deny-list. | [`05`](../specs/2026-07-11-work-assistant-mode/05-work-capture-ontology.md) | **HIGH** |
| **WS-1.6** | **Capture-decision data path** — persist/emit the per-turn decision (today stdout-only, discarded) + read path + home-strip chip **with reason**. | [`05`](../specs/2026-07-11-work-assistant-mode/05-work-capture-ontology.md) §Q7 | S |
| **WS-1.7** | **Session** — assistant template (tenant-neutral; server stamps per-user ids), **no charter (D13)**, **advisory-lock write serialization**, voice affordance hidden. | [`02`](../specs/2026-07-11-work-assistant-mode/02-assistant-mode-session.md) | M |
| **WS-1.8** | **Distiller-lite** — map-reduce → **draft entry** (no extraction yet); durable chunk checkpoints; bounded catch-up sweep (**period digest** for >5-day gaps); giant-paste guard; **injection-laundering** guard (structured output, not free prose); language directive. | [`06`](../specs/2026-07-11-work-assistant-mode/06-journal-distiller.md) | **HIGH** |
| **WS-1.9** | **`chat_search_sessions`** — chat-service's **first MCP server** + gateway registration (`chat_` prefix) + trgm index; enum'd scope; data-not-instructions. | [`07`](../specs/2026-07-11-work-assistant-mode/07-recall-search.md) | M |
| **WS-1.10** | **FE shell** — nav row + **5th C22 intent (BL-15 amendment)** · **tail-first message loading** (an all-day session is otherwise unreadable) · responsive shell (drawer/bottom-nav) · ChatView mobile pass · **home strip**. | [`13`](../specs/2026-07-11-work-assistant-mode/13-frontend-shell-mobile.md) | **HIGH** |
| **WS-1.11** | **Reflection-lite** — `reflection_notes` table + the end-of-day went-well/to-improve capture. (**Not** coaching — see [`08`](../specs/2026-07-11-work-assistant-mode/08-coaching-reflection.md) R4.) | [`08`](../specs/2026-07-11-work-assistant-mode/08-coaching-reflection.md) | S |

**Phase-1 exit — the S14 black-box scenario** (clone S06 discipline, mid-tier local model):
first-run intent → provision → a scripted work day → capture lands work entities (visible on the home strip
**with a reason**) → "End my day" → draft entry with the correct `entry_date` → user keeps it →
**next-day session answers "what did I tell you about the launch?"** (via `chat_search_sessions` — the KG is
still empty in P1, and that is the honest week-1 story).
Plus: **jargon deny-list** · ≥100-message reload shows the **latest** turn (desktop **and** mobile) ·
two-device concurrent send · consent off mid-day stops capture next tick · **a non-assistant session returns
zero diary entities** · every egress path rejected · kill the provisioner after step 1 ⇒ **zero** chat_turn
extraction jobs.
→ **`/review-impl`** → fix → re-verify → commit.

---

## PHASE 2 — KG facts, review surface, erasure, spend

| WS | Scope | Spec |
|---|---|---|
| **WS-2.1** | **`statement` fact type** — CHECK widen (idempotent DROP-then-ADD) + `Literal`s across ≥5 sites + `PendingFact.session_id: str \| None` **in the same change** (else the LIST endpoint 500s). | [`05`](../specs/2026-07-11-work-assistant-mode/05-work-capture-ontology.md) |
| **WS-2.2** | **pending-facts extension** — structured s/p/o + `event_date` + chapter provenance + **dedup key** (+ a **rejection tombstone** — reject is a hard DELETE today, so the same fact is re-proposable immediately). | [`05`](../specs/2026-07-11-work-assistant-mode/05-work-capture-ontology.md) |
| **WS-2.3** | **Divert-to-inbox extraction mode** — assistant projects write to the inbox, never `pending_validation=False`. Per-project destination policy. | [`05`](../specs/2026-07-11-work-assistant-mode/05-work-capture-ontology.md) |
| **WS-2.4** | **The temporal fix** — `valid_from_ordinal = days_since_epoch(entry_date)` **NOT NULL** · a **date-filtered `:Fact` read** (net-new) · the diary writer creates the **`:ABOUT` edge** · assistant path **never** passes `maintain_chain=True` (its key is (subject, fact_type) — it would blind-close unrelated decisions). | [`07`](../specs/2026-07-11-work-assistant-mode/07-recall-search.md) |
| **WS-2.5** | **Review surface** — the kind-adapted diary GUI: keep-entry + entity inbox + fact inbox, **mobile**, bulk ops, **≤10 decisions/day** budget. | [`03`](../specs/2026-07-11-work-assistant-mode/03-book-kinds-diary-gui.md), [`13`](../specs/2026-07-11-work-assistant-mode/13-frontend-shell-mobile.md) |
| **WS-2.6** | **D17 — memory amendment** (the primitive four cases collapse into): **amend the entry revision → re-index → reconcile the graph.** Verbs: correct-a-memory · forget-a-person · supersede. | [`09`](../specs/2026-07-11-work-assistant-mode/09-settings-consent-privacy.md) §Q8 |
| **WS-2.7** | **D18 — erasure** — the **purge worker** (chapters are never row-deleted today) · the **erasure job** (`remove_evidence_for_natural_key` **then** `cleanup_zero_evidence_nodes`) · day-scoped deletes incl. **`usage_logs`** (they hold the decryptable diary text), `compact_summary`, glossary `evidences`, **MinIO objects** · **erasure log replayed after restore**. | [`01`](../specs/2026-07-11-work-assistant-mode/01-data-architecture.md) §8 |
| **WS-2.8** | **Spend lane** — generic lane column ×3 tables · **daily**-window sub-cap · lane tag through `job_meta` across every hop · **the degrade ladder** (background stops, foreground survives, day queued, never silent). | [`10`](../specs/2026-07-11-work-assistant-mode/10-cost-spend-lane.md) |
| **WS-2.9** | **Egress disclosure** — per-turn "don't remember this" (wired into the distiller too) · *"your diary will be sent to &lt;provider&gt;"* with effective value + source tier · **cross-provider fallback requires explicit confirm**. | [`09`](../specs/2026-07-11-work-assistant-mode/09-settings-consent-privacy.md) §Q6 |
| **WS-2.10** | **Employment epoch** — job change closes the epoch; recall defaults to current; export-then-purge at the boundary. | [`09`](../specs/2026-07-11-work-assistant-mode/09-settings-consent-privacy.md) §Q9 |

**Phase-2 exit:** *"What did **&lt;colleague&gt;** **say** about **&lt;topic&gt;** last month?"* returns the right
dated, attributed facts · contradictory facts surface as a **supersession**, not two truths · **"delete my day"
leaves nothing** (asserted: the `chapters` row is **gone**, the `:Fact` node is **absent**, and a KG rebuild
does **not** resurrect it) · "forget this person" works · the cap dying at 2pm degrades, never kills ·
≤10 decisions on a typical day. → **`/review-impl`** → commit.

---

## PHASE 3 — Scheduler & proactive · PHASE 4 — Voice · PHASE 5 — Coaching

| Phase | Scope | Gate |
|---|---|---|
| **P3** | Per-user scheduler (`scheduled_agent_runs` + tick driver, copying the authoring-run driver's heartbeat/budget/breaker) · auto end-of-day · **costed** weekly/diary rollups · nudges. **Unattended writes are draft-into-inbox** (headless runs cannot pass confirm gates). **Notifications are content-free.** Away-marker so a holiday isn't a "journaling gap". | scheduled distill produces a **draft** · a nudge contains **zero** diary content |
| **P4** | Voice parity — route the transcript through the **text agent loop** (so voice gets tools + capture + budget frames) · **fix the 0/0 billing** (a voice day is currently unbilled) · audio retention + erasure. Preconditions: the voice two-stores deferral resolved. **Never ambient.** | a voice turn fires capture, is **billed with real tokens**, and can call a tool |
| **P5** | Coaching — **gated behind four prerequisites** (R4): the commitment/thread **schema** (3 of 4 detectors have no substrate today) · the **judge≠actor** split (`evaluate.py` scores with the session's own model) · the **safety layer** (zero distress handling exists platform-wide) · a **numeric eval bar** (IRR, ≥3 runs, range-not-point-estimate; scores are quarantine-tier until it clears). | no rubric ⇒ no score · a distress diary **short-circuits** the pipeline · the assistant **refuses** to grade a meeting it never observed |

---

## Build order

```
PHASE 0  (prereq, platform)      →  PHASE 0.5 (live privacy holes; can run in parallel)
      ↓
PHASE 1  (MVP: WS-1.1 → 1.11; 1.2 gates everything privacy-touching)
      ↓
PHASE 2  (facts · erasure · spend · amendment)
      ↓
PHASE 3 (scheduler)  →  PHASE 4 (voice)  →  PHASE 5 (coaching)
```

**Parallelizable within a phase** (disjoint files): WS-1.1/1.3 (schema) ∥ WS-1.9 (chat MCP) ∥ WS-1.10 (FE).
**Serialize:** anything touching the extraction chain (WS-0.6 → 0.8 → 2.3 → 2.4).

## The five things most likely to go wrong (watch these)

1. **WS-0.6/0.7** — the publish gate is duplicated in more places than we found. **Grep before each slice**, don't trust the list.
2. **WS-1.2** — an egress path we haven't enumerated. Treat D16 as a **taint rule**, not a checklist; test LIST/SEARCH surfaces, not just per-resource fetch.
3. **WS-1.8** — the distiller on a real 8-hour day (window overflow, giant paste, a crashed reduce).
4. **WS-2.4** — the ordinal/`:ABOUT`/date-filter fix. If recall still returns nothing, **the feature has no value**; smoke it end-to-end early.
5. **WS-2.7** — erasure. The tests must assert **absence** (row gone, node gone, rebuild doesn't resurrect), never "invisible".

## PO decisions — **SEALED** 2026-07-11

All resolved in [`DECISIONS-SEALED.md`](../specs/2026-07-11-work-assistant-mode/DECISIONS-SEALED.md)
(4 PO answers + 23 technical calls). The four that changed this plan:

| # | Decision | Effect on the plan |
|---|---|---|
| PO-1 | Platform privacy holes **fold into Phase 1** | Phase 0.5 dissolved → **WS-1.2**. Accepted risk: the holes are live until P1 lands |
| PO-2 | **Envelope encryption is a P1 requirement** | **New WS-1.0, ships first.** Search becomes a **blind index**. Residual risk (running-server operator; plaintext embeddings) recorded, not papered over |
| PO-3 | **Earn-trust auto-accept + version control** | Amends the LOCKED write-gating law. **D17 (memory amendment) is promoted** — it *is* the revert mechanism, so **auto-accept cannot ship before it** |
| PO-4 | **Keep everything until deleted** | **D18 erasure becomes a release requirement**, not P2 polish — it is now the *only* minimization story. Backup-resurrection must be solved |

**Still open (does not block Phase 0):** embedding exposure — accept plaintext embeddings for the assistant
project (keep semantic recall), or drop semantic recall for the diary (lexical + KG only).
See `DECISIONS-SEALED` Part D.
