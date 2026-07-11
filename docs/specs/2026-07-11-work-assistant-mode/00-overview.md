# Spec: Work Assistant Mode — an all-day personal work companion

**Date:** 2026-07-11 · **Branch:** TBD (`feat/work-assistant-mode`) · **Size:** XL umbrella (spec + per-phase
plans required; each phase lands as its own M/L effort). **Status:** CLARIFY/DESIGN **v3** — v1 was
adversarially reviewed by 5 cold-start lenses (6 P0 + 20 P1 findings, all folded in — see §13 review record);
**v3 (PO direction) generalizes the one-off `purpose='journal'` marker into a first-class `books.kind` enum
(novel/document/lore/diary/…), reuses the existing book GUI for the diary (no new book route), and defines the
diary publish-block precisely (§4.1.2) so it blocks public sharing without killing the internal finalize→KG
extraction trigger.** Pending PO sign-off.

> ### ⚠️ v4 — RED-TEAMED (2026-07-11). Read [`RED-TEAM-2026-07-11.md`](RED-TEAM-2026-07-11.md) before building.
> Four adversarial reviewers + 2 verifiers found **18 P0s** across the three new specs, all code-verified.
> Load-bearing corrections now folded into the decisions below: **D6** was fail-**open** on a privacy flag ·
> **D9**'s temporal model was backwards (a NULL ordinal makes diary facts **invisible to recall** and disables
> the only supersession engine) · **D10** guarded **2 of 7** egress paths (the wiki would auto-publish AI
> biographies of real colleagues; a public MCP key reads the whole diary) · and three brand-new locked
> decisions — **D16 diary-taint**, **D17 memory amendment**, **D18 erasure is unbuilt** — replace what were
> five separate patches.

**Feasibility basis:** 6-area codebase mapping (2026-07-11) + industry research (Zep/Graphiti temporal-KG
convergence; Limitless/Rewind ambient-capture failure; digest-first daily-journal pattern). Verdict: the
*mechanisms* are ~70–80% shipped; the review found that several *seams* the mechanisms need (per-source
extraction gate, inbox landing mode, internal write routes, tail message loading, timezone) are net-new and
are now scoped honestly below.

---

## 1. What this is

A logged-in user opens **Assistant** from the navigation bar and gets a persistent chat (+ voice, P4)
session they can keep open through a working day. While they work *with* the assistant, the platform:

1. **Collects** work knowledge passively (colleagues, projects, decisions, tasks) into human-gated inboxes;
2. **Journals** the day into a private "Work Journal" book (a distilled daily entry, not a raw transcript);
3. **Builds a KG** from the journal so knowledge accumulates queryably over weeks;
4. **Recalls** on demand ("what did Alice say about the Q3 budget last month?");
5. **Helps and coaches** — drafts deliverables, evaluates work, practices communication skills.

**Week-1 value promise (before the KG accumulates):** day 1, the assistant already (a) searches everything
you've ever told it (`chat_search_sessions` raw recall works immediately), (b) shows "what I know about
your work" from promoted entities, and (c) produces the first "End my day" journal draft (distiller-lite
ships in P1). The KG-powered recall deepens from P2 onward. The empty-KG home-strip state is designed, not
accidental (§4.6).

## 2. Locked decisions

| # | Decision | Why |
|---|---|---|
| **D1** | **Memory IS the existing KG.** No new memory subsystem. | Inherited lock (2026-07-09 investigation); industry converged on the same shape (Zep/Graphiti temporal KG). |
| **D2** | **Chat-scoped capture only.** The assistant learns from what the user tells it — never ambient/open-mic recording, never screen capture. | Consent is intrinsic (a diary posture). Ambient capture killed Limitless in the EU/UK/BR; third-party consent liabilities we refuse. |
| **D3** | **Digest-first.** Journal entries are *distilled summaries*. Raw transcript lives only in `chat_messages`. | Storage, privacy surface, and the "shadow work" lesson: the digest is the product, the log is a liability. |
| **D4** | **Every unattended write is draft-into-inbox.** Entity capture → glossary ai-suggested inbox; facts → pending-facts inbox (via a NEW divert-to-inbox extraction mode — §4.2); diary entries → `draft` until the user keeps them. | INV-1..9 + the headless constraint. NOTE (review): the *existing* publish→extraction chain writes facts to Neo4j as trusted (`pending_validation=False`) — the inbox landing mode is net-new P2 work. For the diary, extraction fires on entry *finalize/save* (D15), not publish; the inbox gate is unchanged. |
| **D5** | **Work ontology is data, not schema.** System-tier seed (colleague, project, meeting, decision, task, term, org) via existing kinds/kg_graph_schemas tiering. | The customizable-ontology mechanism exists. EXCEPTION (review): the **`statement` fact type** ("X said Z") IS a schema change — `knowledge_pending_facts` CHECK + `FACT_TYPES` Literals across ≥5 sites + historical-CHECK-backfill migration. Counted in P2. |
| **D6** | **One extraction source per fact, by cost tier.** LIVE: entity capture on the canon-capture cadence. BATCH: fact extraction runs on the *confirmed diary entry* (once/day), never per chat turn. The per-source gate is **DERIVED, and fails CLOSED**: `NOT is_assistant AND chat_turn_extraction_enabled` — never a storable `DEFAULT true` copy. | Kills double-count and caps spend. ⚠️ v2 specced `chat_turn_extraction_enabled DEFAULT **true**` — **fail-open on a privacy flag**, on the *exact table* that already shipped this bug and carries a self-disarm migration for it (`canon_capture_enabled` is `DEFAULT false` + a corrective block). With a partially-failed provisioning (E3 admits it), **every turn of the all-day session would be extracted as trusted canon** — precisely what D6 exists to prevent (red team T7). Consulted in `handle_chat_turn` **and** worker-ai's drainer; one-sided wiring = silent-success bug. |
| **D7** | **Consent has ONE home and fails closed.** The consent switch IS `knowledge_projects.canon_capture_enabled` on the work project — the flag the per-turn gate already re-reads via `kctx` every turn. The assistant settings UI reads/writes that flag (through knowledge-service) and shows it with source chips. Deploy env flag remains a pure ceiling (`effective = AND(deploy, project_flag)`). **No session-tier widen**: a session may only narrow (pause capture for a session), never enable it when the project flag is off. | One-home/one-name (SET rules). v1 put consent in the chat-prefs cascade — a third home the gate never read, so mid-day revocation silently didn't stop capture (review P0). This wiring makes E10 true *by construction*. |
| **D8** | **No scheduler dependency in P1/P2.** Distillation triggers on explicit user action / session close / next-open catch-up **sweep of ALL undistilled days**. Scheduler is P3. | The scheduler is the one true platform hole; decoupling makes the MVP shippable. Sweep-all (not "last active day") closes the midnight-crossing hole (E1). |
| **D9** | **Wall-clock is the valid-time axis — and diary facts MUST carry a story-ordinal too (v3 correction).** Entries carry `entry_date`; facts set `event_date_iso` **and `valid_from_ordinal = entry_date as days-since-epoch` (NOT NULL)**. ⚠️ v2 said "recommend NULL ordinal" — **that was actively wrong**: a NULL ordinal makes a fact **invisible to every entity-anchored recall path** (`f.from_order <= $before_order` drops NULLs, and `$before_order` is never None in production), and it **disables `maintain_chain`**, the only supersession engine — so contradictions ("launch is Friday" → "Tuesday") would both stay open forever. A date-filtered `:Fact` read + the `:ABOUT` edge are **net-new** (today `event_date_iso` on `:Fact` is a *sort* key, never a filter). Per-user IANA timezone + day-cutoff is net-new; **`chat_messages.local_date` is stamped at WRITE time** so a later tz change can't re-bucket history. | Red team T3/T4/T21. Without this, *"what did Alice say last month?"* — the headline promise — **has no query that can answer it**. |
| **D10** | **The diary is un-shareable on every path — see D16.** `books.kind='diary'` is immutable and server-set, enforced by a **DB `BEFORE UPDATE` trigger** (not a convention — the two dynamic UPDATE allowlists would otherwise be the only guard). Guarded paths: (a) both collaborator write handlers; (b) sharing-service `patchSharingPolicy` (live lookup per PATCH — it serves from a cached policy row otherwise); (c) **the wiki** — `wiki_settings` PATCH, `generateWikiStubs`, `entity_enrichments`, and `checkWikiPublic` fail-closed; (d) **the public MCP gateway**; (e) notifications; (f) library/catalog listings; (g) export. Consumed-by-effect test **per path**. | v2 guarded **2 of 7**. The red team walked out through the other five — the worst being the **wiki** (auto-writes AI biographies of real colleagues, servable **unauthenticated**) and the **public MCP gateway** (a `domain:book` key reads the whole diary and can write to it). |
| **D11** | **Voice is P4 — and voice input is disabled (hidden) for assistant-bound sessions until then.** Preconditions: voice-path parity (tools + capture on voice turns), the voice 0/0-token billing fix (verified real: `voice_stream_service` logs zero usage), two-stores deferral resolved. | v1 deferred voice but left the shared ChatView's voice overlay reachable — voice turns would be journaled yet silently uncaptured and unbilled (review). Hiding the affordance is honest; the distiller includes voice turns when P4 enables them. |
| **D12** | **Reuse the chat GUI** — assistant = a session rendered by ChatView, entered from a new nav item + a fifth C22 onboarding intent. Mobile = a scoped FE track (§4.6), not a separate app. | The GUI exists, but "all substrate shipped" was false in one core place: **the FE loads only the first 50 messages with no tail mode** — an all-day session is unreadable on reload. Tail-first loading is a named P1 work item. |
| **D13** | **The main assistant session carries NO working-memory charter.** Persona/steering ride the system prompt + book steering rules. The charter → executive-tick → scorecard pipeline is reserved for *coach sessions* (§4.5). | The executive tick fires an extra LLM call every 4th turn on any charter-carrying session — all-day that is ~N/4 uncounted calls stacked on capture's identical cadence (review). Coach sessions are bounded; the all-day session must not tick. |
| **D14** | **First-class `books.kind` enum — reuse the book GUI, branch on kind.** Closed set `novel` (default) · `document` · `lore` · `diary` (extensible via CHECK migration). The diary reuses the EXISTING book workspace/editor route (`/books/:id`) with kind-conditional rendering (entry vocabulary, no publish/share UI, diary-specific bits) — **no new book route**. `is_bible` books backfill to `kind='lore'`; `is_bible` stays as the orthogonal hidden-container flag (not unified in this spec). | Generalizes the v2 one-off `purpose='journal'` marker (PO direction). `is_bible` is the exact precedent (a flag added by ALTER for a special book kind). Reusing the book GUI avoids forking ChapterEditorPage / the workspace. |
| **D16** | **⭐ Diary-taint propagation (LOCKED).** A row **derived from** a `kind='diary'` source is **diary-tainted**. Diary-tainted rows are excluded from **every** list · search · export · notification · public-MCP surface **unless the caller is the owner in an assistant context**. Taint propagates to derived stores: KG facts/entities, glossary entities, wiki articles, enrichments, notification bodies, library/catalog listings. Concretely: `memory_*` must **require an explicit project scope** for tainted data (today `memory_recall_entity`/`memory_timeline` **silently fall back to ALL the user's projects**, and `get_entity_with_relations` has **no project filter at all** — so the diary leaks into a novel-writing session); diary-sourced notifications are **content-free**; the diary is hidden from the library grid. | The red team's key structural insight: **three P0s were the same shape** — a *derived* store inheriting a permission only ever enforced at the *authored* store (`books`). D10 guarded `books`; the KG, the glossary, the wiki, the public MCP surface, and notifications are each a separate egress with their own rules. One rule closes T1, T17(wiki), T22, T26, T27, T40 — worth a locked decision, not five patches. |
| **D17** | **⭐ Memory amendment — one primitive, four verbs (LOCKED).** *Supersede a fact · correct a memory · forget a person · merge a renamed entity* are all the same **three-legged write**: **(1) amend the PG SSOT (the diary entry revision) → (2) re-index (`chapter.kg_indexed`) → (3) reconcile the derived graph.** Anything that stops at leg 3 is a lie. | Today there is **no correction path at all**: `memory_forget` invalidates one Neo4j fact, never touches PG — so the diary text stays wrong, and a KG rebuild **resurrects** the "corrected" fact. Pending-fact reject is a **hard DELETE with no tombstone** (re-proposable immediately). Entity-delete → KG has **no cascade and no event type**. Leg 3 mostly exists; **leg 1 is missing and nobody noticed** because `memory_forget` *looks* sufficient. Build once — T4/T10/T24/T25 collapse into one tested path. |
| **D18** | **Erasure requires machinery that does not exist yet.** (a) **Chapters are never row-deleted** — "delete" is a soft transition to `purge_pending` and **no purge worker exists**, so every `ON DELETE CASCADE` in the copy-set is **inert** and the diary text survives forever. (b) `handle_chapter_deleted` leaves `:Fact`/`:Entity` nodes at `evidence_count=0` **with content and embeddings**, and `merge_fact`'s natural key means a later mention **resurrects** them. (c) `usage_logs` hold the **decryptable prompt text** (= the diary content) with no `book_id` to delete by. | "Delete my day" is not a P2 polish item — it is **unbuilt infrastructure**. Erasure tests must assert the row is **gone**, not `purge_pending`, and that a KG rebuild does not resurrect. |
| **D15** | **KG extraction is decoupled from publish — platform-wide (§4.7).** Publish no longer gates extraction for *any* kind. Extraction is driven by a per-chapter **indexed-revision pointer** (generalizes today's `published_revision_id`); an explicit **"index / add to knowledge"** action sets it — on a draft or a published chapter, for any book kind, without requiring publish. Publish still pins & indexes (backward-compatible), but a writer who only drafts can index too. Churn control: indexing fires on the explicit action or an idle-debounce, **never on every draft autosave** (each save already snapshots a revision — per-save extraction would thrash). The diary is the first consumer: "keep entry" sets the pointer, no publish. | "Publish required is not fit anymore; writers draft and want KG without publishing" (PO). This is a **platform change to the book↔knowledge extraction contract** (book-service revision + its own KG staleness sweep + a NEW `chapter.kg_indexed` event; knowledge-service handler), not a one-liner. The data-arch map corrected two things: the trigger is a **new** event (`chapter.kg_indexed`), never the existing `chapter.saved` (which fires on every autosave and was deliberately un-consumed); and the KG staleness needs its **own** sweep pointer, not a re-key of `last_parsed_revision_id` (the scenes marker). Gets its own plan (§4.7); over-extraction risk is managed by the explicit/idle trigger + revision-idempotent caches. |

## 3. What already exists — corrected reuse map

| Piece | Where | Reuse status (post-review) |
|---|---|---|
| Sessions + settings cascade (effective-value + source-tier contract) | chat-service `settings_resolution.py`, `ai_settings.py` | ✅ reuse; **assistant category = new JSONB column + patch-model fields + session-override column** (prefs store per-category *columns*; an undeclared category is silently dropped — known bug class) |
| Canon-capture spine (cadence gate → extract → inbox → tombstones) | `canon_capture.py`, glossary `capture_canon_handler.go` | ✅ reuse; new `flavorWorkCapture` — **flavor server-resolved from book `kind`** (extend the internal access contract to return `kind`; a caller-supplied flavor arg is forbidden). Capture bills at the **session's model** (no cheap-tier routing exists) — honest cost note in §6; optional cheap capture-model role is P2 |
| Pending-facts inbox + PendingFactsCard | knowledge-service, chat FE | ⚠️ **schema extension required**: nullable `session_id`, chapter/provenance ref, structured subject/predicate/object/`event_date` fields, `statement` fact type (CHECK backfill discipline) |
| Publish→extraction | knowledge-service handlers, worker-ai | ⚠️ existing chain **auto-canons** (`pending_validation=False`) and **skips projects with no prior extraction job** (drainer `if last is None: continue`). P2 builds: divert-to-inbox mode for assistant projects + provisioning bootstraps extraction config, else publish silently no-ops |
| Hierarchical summaries | `summary_processor.py` | ⚠️ daily publish (scope `chapters_pending`) produces the **chapter summary only** — part/book rollups fire only on whole-book passes, and their md5 cache misses every day a chapter is added. Weekly/whole-journal rollups = explicit P3 deliverable with its own cost line |
| memory_search / recall_entity / timeline (date-range), owner-only | knowledge-service MCP | ✅ reuse unchanged |
| Compact summarizer | `compact_service.py` | ⚠️ single-call, `max_tokens=1400`, **raises `SummaryTruncatedError` on overflow** — cannot eat a day. Distiller = **map-reduce job** (§4.3) reusing worker-ai's model-context-aware chunking |
| Roleplay charter + tick + scorecard | chat-service | ✅ reuse **for coach sessions only** (D13) |
| Spend guardrails | usage-billing `guardrail.go` | ⚠️ the mcp-key sub-cap is **monthly-windowed, UUID-column-specific, caller-carried** — the assistant lane is its own M-sized P2 item (§6) |
| Session templates | chat-service `session_templates` | ⚠️ System-tier rows are tenant-shared and have **no project/book/skills columns** — templates carry tenant-neutral content only; per-user ids are stamped onto the `chat_sessions` row at session-create (it HAS `project_id`/`book_id`/`enabled_skills`) |
| Book/chapter write path | book-service MCP tools | ⚠️ MCP tools are user-context; book-service `/internal` is **read-only**, knowledge project create is public-only, worker clients can't write. Distiller + provisioning need **named new seams** (§4.1.1, §4.3) |
| Auth-gated nav + C22 intent fork | `Sidebar.tsx`, onboarding | ✅ nav row trivial; **fifth intent ("get help with my work") = explicit BL-15 amendment**, recorded as a decision |
| Black-box eval harness | `run_discoverability_scenario.py` | ✅ reuse for S14 |

## 4. Architecture

### 4.1 Assistant mode & session (P1)

- **Nav entry:** `Assistant` in `mainNav` (auth-gated) → `/assistant`; plus the fifth C22 onboarding intent
  routing here (BL-15 amendment). The route resolves/provisions the assistant context and opens the current
  assistant session in ChatView.
- **Session binding (corrected):** the System-tier assistant template carries only tenant-neutral content
  (persona prompt, skill codes, capture defaults). At session-create, the server resolves the caller's
  provisioned resources and stamps `project_id` (work project), `book_id` (journal), `enabled_skills` onto
  the `chat_sessions` row. A System row never stores per-user ids (User Boundaries law).
- **Assistant-session predicate:** `chat_sessions.book_id = the user's journal book` (or an additive session
  `kind` column if implementation prefers — decide in the P1 plan). Needed by `chat_search_sessions` scoping
  and the voice-disable gate (D11).
- **Same-session concurrency (multi-device):** message writes serialize per session — pg advisory lock
  around sequence-assign + insert, retry-once on unique violation (the `MAX+1` seq assignment is otherwise
  a designed-steady-state race that silently drops the losing turn). Two-writer live-smoke in S14.

#### 4.1.1 Provisioning (idempotent, race-safe)

`POST /v1/assistant/provision`. **Identity:** the provisioned `owner_user_id` for every row is the
gateway-authenticated principal, propagated end-to-end; every downstream route owner-keys/grant-checks it
(capture-canon pattern); a cross-user id in any body is rejected.

**Seams (named net-new work):** book-service `/internal` is read-only and knowledge project create is
public-only today. Provision orchestration lives in **api-gateway-bff fanning out over the public APIs with
the user's JWT** (preferred — no new internal write surface), or new grant-checked `/internal` write routes
if the BFF path proves awkward; decided in the P1 plan.

**Steps (each an atomic upsert against an explicit idempotency key — two concurrent provisions converge):**
1. Diary book (`kind='diary'`, holds the daily work-journal entries): partial unique
   `UNIQUE (owner_user_id) WHERE kind='diary' AND lifecycle_state='active'`, `ON CONFLICT` repeating that
   exact predicate. `kind` is immutable, server-set (§4.1.2).
2. Work knowledge project referencing the diary book: equivalent one-per-user partial unique; additive
   purpose/`is_assistant` marker column (the closed `project_type` CHECK is NOT extended — avoids the
   enum-backfill migration). Extraction is kind-driven (D15): the project is armed for save-triggered
   extraction, not publish.
3. Work ontology seed (kinds + kg_graph_schemas adopt — existing paths).
4. **Extraction bootstrap:** store the project's extraction config (resolved distill/extraction model +
   spend cap, status transition) so the publish drainer is armed — without this, journal publishes enqueue
   rows that are never drained (silent no-op, review).
5. Timezone: seed from client `Intl` zone, explicit user confirm (D9).
6. Capture consent: enabled **only** if the user turns it on (D7 — the toggle writes the project flag);
   never flipped as a provisioning side effect.
7. Today's assistant session from the template (per §4.1 binding).

**Journal-book trash:** get-or-create matches active-only but **detects** a trashed journal and offers
restore vs. re-provision-fresh — never silent resurrection, never a silent fork (dangling KG anchors noted
on the §7 track). Trashing the journal from the library triggers an assistant-aware confirm and pauses
distill/capture.

### 4.1.2 Book kinds & the diary publish-block (D14/D15)

**`books.kind`** — additive `TEXT NOT NULL DEFAULT 'novel'`, CHECK `kind IN ('novel','document','lore',
'diary')` (closed set; adding a kind = a CHECK migration). **Immutable after creation** (server-set); a
`kind='diary'` book can never be converted to another kind (the D10 privacy lock depends on it).
**Backfill:** `UPDATE books SET kind='lore' WHERE is_bible=true` — the `DEFAULT 'novel'` does NOT
retroactively fix bible books (the ADD-COLUMN-won't-revisit-default lesson), so the migration sets it
explicitly; all other existing books → `novel`. `is_bible` remains the orthogonal hidden-from-counts flag.

**Reuse, don't fork (D14):** the diary uses the existing book workspace (`/books/:id`), entries list, and
chapter editor, rendered with `kind='diary'` branches. The assistant *chat* stays at `/assistant` (ChatView
reuse); the diary *book* is browsed/reviewed through the reused book GUI, kind-adapted.

**Diary-kind behavior vs the `novel` default:**

| Feature | novel (default) | diary |
|---|---|---|
| Public sharing (sharing-service visibility) | allowed | **hard-blocked, private-locked (D10)** |
| Collaborator grants | allowed | **blocked (D10)** |
| Chapter "Publish" button / PublishControl | shown | **absent — no publish concept (D15)** |
| KG-extraction trigger | `chapter.published` (canon = published) | **entry finalize/save (D15)** — no publish |
| Vocabulary in the reused GUI | "Chapter" | **"Entry"** (i18n label keyed on kind) |
| `kind` mutability | immutable | **immutable + un-convertible (privacy lock)** |
| Export of own data | allowed | allowed (owner's own data) |

**The finalize→extract seam (replaces "publish under the hood"):** the distiller writes a diary entry as a
draft; the user reviews and **keeps** it (a light "does this look right?" confirm — not "publish"). "Keep
entry" is the diary's flavor of the general **"index / add to knowledge"** action (§4.7/D15): it sets the
chapter's indexed-revision pointer and fires **`chapter.kg_indexed`** (a NEW event — see §4.7), which
knowledge-service extracts from — **no publish, no `editorial_status='published'`**, and using a **new
orthogonal `diary_kept_at` column**, never a third `editorial_status` value. Facts divert to the pending-facts inbox (D4 — the
per-project destination policy). Provisioning still arms the project's extraction config (§4.1.1 step 4),
else the save-triggered drain silently no-ops (ARCH-6/E15). Live entity capture during chat (§4.2) is
independent of the entry finalize.

### 4.2 Capture (P1 = entities, P2 = facts)

- **Live entity capture (P1):** canon-capture with `flavorWorkCapture` (captures real-world work entities;
  meta/small-talk excluded). Flavor selected **server-side** in glossary from book `kind` (via the extended
  internal access contract) — never a caller-supplied arg. Cadence/caps/tombstones/grant posture unchanged.
- **Capture-decision surfacing (P1 work item):** the per-turn `CaptureDecision` today is stdout-only and
  discarded by the caller. P1 persists/emits it (session-scoped record or stream event) + a read path + the
  home-strip chip consuming it, with a consumed-by-effect test ("chip shows fire=false reason=off_cadence").
  Without this the "collecting" chip is the shipped-twice silent-no-op bug.
- **Self-feeding guard (mechanism, not hand-wave):** capture SKIPS turns whose persisted `tool_calls`
  include journal/chapter-read or recall tools (provenance is already stored per message); the distiller
  prompt excludes assistant-quoted journal/recall content; pending-facts gains a dedup key for
  cross-chapter duplicates. S14 test: quote yesterday's entry ⇒ no new candidates, no duplicate facts.
- **Daily fact extraction (P2):** on journal-entry confirm, extraction runs with the work ontology in a NEW
  **divert-to-inbox mode** (assistant projects write extracted facts/relations to the extended
  pending-facts inbox, never `pending_validation=False` Neo4j writes). Attributed dated statements
  (`subject=colleague, predicate=stated/decided/committed, object, event_date_iso=entry_date`) use the new
  `statement` fact type (migration per D5). Per-turn `chat_turn` extraction disabled via the new per-source
  gate (D6).

### 4.3 Journal (distiller-lite in P1; extraction hookup in P2)

- **Triggers (D8):** "End my day" button; session archive; on any assistant open, a catch-up **sweep of all
  undistilled local dates** that have messages (distinct local dates in `chat_messages` minus existing
  `entry_date`s). Message→day assignment: `created_at` in the user's zone with the day-cutoff (D9).
- **Idempotency (mechanism):** additive `chapters.entry_date` + `journal_kind` (`primary`|`supplement`);
  partial unique `(book_id, entry_date) WHERE journal_kind='primary' AND lifecycle_state='active'` with
  `ON CONFLICT` repeating the predicate; job-level advisory lock keyed `(user, entry_date)` so concurrent
  triggers coalesce. Re-distill before confirm extends the primary draft; after confirm, a re-run creates a
  `supplement` draft (the partial index exempts supplements by design).
- **Distiller = map-reduce background job** (worker-ai shape): chunk the day's messages into
  model-context-sized windows (reuse worker-ai's chunk sizing), per-chunk FACTS extraction, one reduce call
  into the entry draft with a raised output budget and partial-day resume. Typical 3–15 calls/day (§6) —
  the single-call compact summarizer (1400-token cap, raises on overflow) is the prompt *shape* only.
- **Write seam (named):** a new internal-token, owner-scoped, **draft-only** chapter-write route (+ a
  day-window internal chat-messages read) for the worker — book-service `/internal` has no write today.
  Grant-checked per the `/internal` lesson.
- **Model home:** `assistant.distill_model` (Account tier, ModelRole cascade) → fallback to the user's
  chat-capability default → **fail visibly** on the home strip when neither resolves ("cheapest capable"
  auto-ranking does not exist and is not promised).
- **Language:** the distiller resolves the user's language (same source the roleplay charter's `Respond in:`
  uses) and the prompt carries an explicit "write the journal in <lang>" directive. S14 includes a VI work
  day ⇒ VI journal case.
- **Keep/confirm is human-gated (D4)** through the kind-adapted diary book GUI (§4.1.2/§4.6) — entry
  vocabulary and a light "does this look right?" review, NOT the writer's publish flow. "Keep entry" =
  finalize → `chapter.kg_indexed` → extraction (divert-to-inbox, P2); **there is no publish step (D15)**. Daily
  finalize yields the **entry summary only**; weekly/whole-diary rollups are a P3 deliverable.

### 4.4 Recall (P1)

- Existing `memory_*` tools + grounding unchanged. (Honest note: the KG is structurally empty until P2
  journals accumulate — §1's week-1 story leans on the next bullet.)
- **`chat_search_sessions`** (new): owner-scoped cross-session search over `chat_messages`. Scoping and
  posture (review-hardened): default `session_scope='assistant'`; `scope='all'` only from an
  assistant-bound session; owner filter = the authenticated user id (never caller-supplied); results are
  **capped excerpts wrapped as data-not-instructions** (capture route's posture); S14 includes a
  stored-injection case (a searched-up message containing an instruction must not be followed).
- **Infra counted honestly:** chat-service today is only an MCP *host* — this tool means chat-service's
  first MCP server + ai-gateway provider registration (policed `chat_` prefix; unprefixed-federation
  lesson) + enum'd `session_scope`. Plus `pg_trgm` extension + GIN trigram index on
  `chat_messages(content)` (the single-session ILIKE justification does not extend to months of history;
  the English tsvector index is useless for VI/CJK — trigram is the point, but only WITH the index).

### 4.5 Task help & coaching (P1 templates; longitudinal = separate CLARIFY)

- Task help: existing agent loop + tools + ChatOutputs, in scope of the assistant session.
- Coaching P1: work-coach `session_templates` (communication practice, meeting debrief, weekly reflection)
  reusing charter → tick → scorecard — **in dedicated coach sessions only** (D13). Template charters set
  `language` from user prefs, not hardcoded.
- Longitudinal evaluation deferred to its own CLARIFY (needs rubric product design + P3 scheduler).

### 4.6 Frontend (P1/P2 — scope split honestly)

1. **P1 — Shell + chat:** nav row; fifth C22 intent; responsive shell (sidebar → drawer/bottom-nav under a
   breakpoint — net-new shared infra); ChatView mobile pass; **tail-first message loading** (server:
   `after_seq`/tail mode; FE: initial fetch = last N + upward "load earlier" via existing `before_seq`) —
   without it an all-day session shows only the morning's first 50 messages on reload.
2. **P1 — Home strip:** capture status chip (fed by the §4.2 decision record — effective value + reason),
   journal draft nudge, "what I know about your work" empty-state (promoted entities), inbox counts.
3. **P1/P2 — Diary review via the kind-adapted book GUI (reuse, don't fork — D14):** the daily "does this
   look right?" review, the entity inbox, and (P2) the facts inbox are surfaced through the EXISTING book
   workspace/editor rendered with `kind='diary'` branches ("Today's entry — keep it?", "People and projects
   I noticed", "Things worth remembering") — plus a light home strip in the assistant chat for quick
   access. Requirements that still bind: **work-domain language only** (S06 no-jargon rule — "Entry",
   never chapter/publish/entity/kind); **mobile-capable** — the diary book workspace + editor must work on
   phone (the companion's device), and the existing writer surfaces are desktop/dockview-shaped, so a
   mobile pass on the reused GUI for `kind='diary'` is real P1/P2 FE work; bulk operations
   (accept-all-high-confidence, reject-all); and a **review-burden budget ≤10 decisions on a typical day**
   (capture caps + batching tuned to meet it; S14 records decisions-per-day).
4. i18n: all new strings through the locale pipeline (`scripts/i18n_translate.py`).

### 4.7 Publish-independent KG indexing (platform change — D15)

**Prerequisite the assistant depends on; broader than the assistant — gets its own plan (and likely its own
spec doc).** Today extraction is welded to publish: the reparse sweeper re-indexes wherever
`last_parsed_revision_id IS DISTINCT FROM published_revision_id` ([reparse_sweeper.go:82]), and only
`mcpPublishChapter` pins `published_revision_id` + emits `chapter.published`. A chapter that is only ever a
draft has `published_revision_id = NULL` and never reaches the KG — even though **draft-saves already
snapshot `chapter_revisions`** (`toolChapterSaveDraft`), so the content to index exists.

**The change (additive, backward-compatible):**
- Introduce a per-chapter **indexed-revision pointer** (`kg_indexed_revision_id`, generalizing
  `published_revision_id` for the KG's purposes) with its **own independent staleness check + sweep arm**.
  ⚠️ NOT a re-key of the existing `last_parsed_revision_id` predicate: that marker is *also* the
  scenes/structural-decomposition freshness signal (a different concern), and the sweeper is hard-gated on
  `editorial_status='published'` — so a draft-only diary entry would never be swept. See
  [`01-data-architecture.md`](01-data-architecture.md) §5.
- An explicit **"index / add to knowledge"** action (MCP tool + book-GUI affordance) points it at the
  chapter's current draft revision and emits a **NEW event `chapter.kg_indexed`** (`{book_id, chapter_id,
  revision_id}`) — **not** the existing `chapter.saved` (which fires on every autosave, payload `{book_id}`,
  and was deliberately un-consumed by knowledge-service to stop drafts canonizing — reusing it would regress
  that guarantee; see §7 of the data-architecture doc). knowledge-service extracts as it does for
  `chapter.published` (same read path, same revision-keyed caches). Works on a draft or a published chapter,
  for any `kind`.
- **Publish still indexes** (it sets the pointer too) — no existing behavior removed; publishing simply
  stops being the *only* way to build the KG.
- **Churn control:** indexing fires on the explicit action or an idle-debounce (e.g. N minutes after the
  last edit), never per-autosave. The existing `extraction_leaves` / md5 caches mean re-indexing an
  unchanged revision is a no-op; the guard is against re-indexing *changed* drafts on every keystroke.
- **Destination policy is orthogonal (D4):** authored books (novel/lore/document) index to trusted canon as
  today; assistant/diary projects divert to the pending-facts inbox. "Where facts land" is the per-project
  policy; "when extraction fires" is this trigger — kept separate.
- **Per-chapter opt-out** (a `kg_exclude` flag) lets a writer keep scratch/spoiler drafts out of the KG,
  replacing the implicit "unpublished ⇒ not indexed" control that publish-gating used to provide.

**Blast radius:** book-service (revision pointer + its own KG staleness sweep, new index action + new
`chapter.kg_indexed` event) + knowledge-service (register a handler for `chapter.kg_indexed` — NOT
`chapter.saved`) + the frontend "add to knowledge" affordance. L-sized; a consumer live-smoke on the new
event (new-cross-service-contract rule). Full deltas + file:line in [`01-data-architecture.md`](01-data-architecture.md).

## 5. Settings (SET-1..8 compliance)

| Setting | Home / tier | Default | Notes |
|---|---|---|---|
| `assistant.enabled` | Account (new `assistant` JSONB column in `user_chat_ai_prefs` + patch-model fields — additive migration) | off | Gates provisioning CTA + assistant surfaces |
| **Capture consent** | **`knowledge_projects.canon_capture_enabled` on the work project — the ONE home (D7)**; assistant UI reads/writes it via knowledge-service; TierChip shows effective value + source | **off** | Fail-closed; per-turn gate already re-reads it (kctx). Session tier may only narrow (pause), never widen |
| `assistant.distill_enabled` | Account (`assistant` column) | off until consent on | Implies spend |
| `assistant.distill_model` | Account (ModelRole cascade) | unset → chat default → visible failure | §4.3 |
| `assistant.spend_cap_usd` | Account | platform default | Consumed by the P2 lane (§6); ceiling-composed with deploy caps |
| `user.timezone` (IANA) + day-cutoff | Account (new — D9) | unset ⇒ UTC + warning chip; auto-distill held | Consumed by all entry_date computation |
| `ASSISTANT_MODE_ENABLED` | Deploy env | on | **Ceiling only** |

All consumed-by-effect (tests assert behavior); effective value + source tier surfaced (TierChip contract).

## 6. Cost envelope (corrected to call units)

For a 150-turn all-day text session (defaults):

| Stream | Calls/day | Notes |
|---|---|---|
| Entity capture | ~N/4 ≈ 30–38 | Bills at the **session's** model (no cheap-tier routing exists; ~$0.2–0.5/day on gpt-4o-class, $0 local). Optional cheap capture-model role = P2 |
| Session compaction | ~turns/8 ≈ 15–20 | `persist_auto_compact` summarizer calls — inherent to the all-day shape |
| Grounding | ~1 embed/grounded turn (+ occasional L2 summarize) | Existing per-turn retrieval cost, now counted |
| Executive tick | **0 on the main session (D13)**; ~N/4 in coach sessions | v1 omitted this stream entirely |
| Distiller | ceil(day_tokens/window)+1 ≈ 3–15 | Map-reduce (§4.3) |
| Publish-extraction (P2) | 4 × ceil(paragraphs/15) + 1 summary + 1 embedding ≈ 6–12; optional gates +1–3 | First extraction always cache-misses |
| Weekly/journal rollups (P3) | ~1 part-summary/week + book rollups whose input grows O(days) | NOT free; md5 cache never hits at part/book level on a growing journal |

**Total ≈ 90–120 background LLM calls/day** (v1 implied ~30–50). Still **$0 on local BYOK**; roughly
$1–3/day on gpt-4o-class. All spend flows through existing USD guardrails.

**Per-feature lane = its own M-sized P2 work item** (not a tweak): a generic feature/lane column on
`token_reservations` + `usage_logs` + provider-registry `usage_outbox`; a **daily**-window sub-cap variant in
`guardrailReserve` (the mcp-key precedent is monthly); the cap resolved from `assistant.spend_cap_usd`; the
lane tag carried in `job_meta` across every enqueue hop (the envelope-drop bug class: gateway drops
X-Project-Id; the mcp-key carrier survives in-process only) with a consumer live-smoke.

## 7. Privacy & retention (cross-cutting track — starts P2; blocks sharing + voice-at-scale)

- Third-party personal data enters only via the user's own account of events (D2), into per-user stores;
  the journal is un-shareable on **all** paths (D10).
- **"Delete my day" — complete copy-set inventory** (v1's was incomplete): chapter drafts + published
  revisions; the chapter summary AND upstream part/book rollups (invalidate incl. md5 cache keys);
  `extraction_leaves` + `extraction_leaves_raw` (raw LLM output holds the fact text);
  `knowledge_pending_facts` rows from the day's batch; Neo4j facts/evidence + embeddings; day-minted
  glossary drafts; `session_working_memory`. Deletion happens at the **PG SSOT and cascades to Neo4j**, with
  a verify step that a KG rebuild does not resurrect.
- **`memory_forget` is NOT an erasure primitive** — it soft-invalidates ONE Neo4j fact (`valid_until`),
  retains content for audit, and never touches PG. Useful for "that's outdated", not for erasure.
- Retention windows (user-set) for assistant sessions + journal; export. Audio policy decided in P4.

## 8. Phasing (post-review scope)

| Phase | Scope | New schema |
|---|---|---|
| **P1 — Assistant MVP + journal-lite** | Nav + C22 fifth intent (BL-15 amendment); **`books.kind` enum + diary kind (publish/share blocks + kind-adapted book GUI: entry vocabulary, no publish UI)**; provisioning (idempotency keys, identity, extraction bootstrap, tz confirm); work ontology seed; `flavorWorkCapture` + kind-resolved flavor (access-contract extension returns `kind`); capture-decision surfacing; assistant settings category; consent one-home wiring; `chat_search_sessions` (chat MCP server + gateway registration + trgm index); **distiller-lite** (map-reduce → draft entry; no extraction yet); tail-first message loading; responsive shell + ChatView mobile pass; home strip; session write serialization; voice hidden in assistant sessions; work-coach templates | `books.kind` enum + CHECK + `is_bible→lore` backfill + partial unique `(owner_user_id) WHERE kind='diary'`; `chapters.entry_date` + `journal_kind` + orthogonal `diary_kept_at` (NOT an `editorial_status` value) + partial unique; `user_chat_ai_prefs.assistant` column (+ session override col); knowledge_projects `is_assistant` marker + partial unique; timezone setting (auth `user_preferences`, TBD); pg_trgm index |
| **Prereq — Publish-independent KG indexing** | **Platform change (§4.7/D15), own plan, L-sized:** `kg_indexed_revision_id` pointer + its own KG staleness sweep (NOT a re-key of the scenes marker); explicit "index / add to knowledge" action (MCP + GUI) + idle-debounce; **new `chapter.kg_indexed` event** consumed by knowledge (NOT `chapter.saved`); per-chapter `kg_exclude`. The diary "keep entry" is its first consumer | `chapters.kg_indexed_revision_id` + `kg_exclude`; new `chapter.kg_indexed` event contract |
| **P2 — KG facts + review surface** | Divert-to-inbox extraction mode (per-project destination policy); per-source gate (`chat_turn_extraction_enabled`); `statement` fact type migration (CHECK backfill + Literals); pending-facts schema extension (structured s/p/o + date + provenance + dedup key); diary facts inbox in the kind-adapted book GUI (mobile, bulk ops, burden budget); per-feature spend lane (M); privacy track starts | pending-facts extension; fact-type CHECK; lane column ×3 tables; gate column |
| **P3 — Scheduler + proactive** | Per-user scheduler; auto end-of-day distill; weekly/journal rollup jobs (costed); notification nudges; assistant studio panel | scheduler tables |
| **P4 — Voice all-day** | Voice-path parity (tools + capture on voice turns); voice usage billing fix; re-enable voice in assistant sessions; audio retention policy | — |
| **P5 — Coaching v2** | Longitudinal evaluation (own CLARIFY) | TBD |

## 9. Non-goals

- Ambient/open-mic/always-listening capture, screen recording, meeting bots (D2 — permanently out).
- Auto-canonizing facts or auto-confirming journal entries (D4; the trust-tier question is §12 Q1, a PO
  decision, not a default).
- A separate assistant surface forked from chat (D12).
- Cross-user analytics over assistant data (tenancy law).
- Real-time same-day KG ingestion (D6 gap, covered by `chat_search_sessions`).
- "Cheapest capable model" auto-ranking (no pricing-rank substrate; explicit settings instead).

## 10. Edge cases & failure modes (post-review)

| # | Case | Handling (mechanism named) |
|---|---|---|
| E1 | Day rollover / stale session / midnight-crossing work | Catch-up **sweeps all undistilled local dates** (not "last active day"); message→day = `created_at` in the user's IANA zone with day-cutoff (D9); tz unset ⇒ UTC + warning chip + auto-distill held |
| E2 | Concurrent "End my day" (two devices) / re-distill / post-confirm additions | Partial unique `(book_id, entry_date) WHERE journal_kind='primary' AND active` + ON CONFLICT on the same predicate + advisory lock `(user, entry_date)`; pre-confirm re-runs extend the primary; post-confirm re-runs create `supplement` entries |
| E3 | Partial provisioning failure / double-tap / two devices provisioning | Every step an atomic upsert against its partial-unique idempotency key; concurrent provisions converge on the same rows |
| E4 | Capture silently not firing (consent off, kinds missing, off-cadence, project unlinked) | **Persisted/emitted per-turn capture-decision record** + home-strip chip with reason (P1 work item — the in-code log is stdout-only and discarded today) |
| E5 | Empty/low-signal day | Distiller gate mirrors capture's ≥-chars gate: below threshold ⇒ no entry, reason logged + surfaced |
| E6 | Multilingual day (VI/CJK) | Work prompt flavors follow the multilingual discipline; **distiller writes in the user's language** (explicit directive); trigram search (indexed); extraction reuses CJK dict-anchor hardening; S14 has a VI case |
| E7 | Inbox flooding | Caps stay + **burden budget ≤10 decisions/day** + bulk ops + ONE daily-review moment (§4.6.3); decisions-per-day is an S14 metric |
| E8 | Multi-device, same session | Server-truth + **per-session advisory-lock write serialization** (the MAX+1 seq race silently drops turns otherwise); distiller unions the user's assistant-session messages by local date regardless of session count |
| E9 | LM Studio wedge / model down | Capture + distiller best-effort background: failures surface on the home strip, never block chat; distiller resumes at next trigger |
| E10 | Consent revoked mid-day | TRUE by construction under D7: the toggle writes the ONE flag the per-turn gate re-reads via kctx ⇒ capture stops next cadence tick. Consumed-by-effect test: revoke mid-session ⇒ next tick logs `consent_off`, no capture call. Already-captured drafts remain (human-gated) |
| E11 | Self-feeding (assistant quotes the journal; distiller re-digests the quote) | Capture skips turns whose `tool_calls` include journal-read/recall tools; distiller prompt excludes quoted journal content; pending-facts dedup key; S14 asserts no duplicates and no wrong-dated re-extraction |
| E12 | Quota pressure | Digest-only entries keep bytes small; storage errors surface on the home strip |
| E13 | Voice input in P1–P3 | Hidden/disabled for assistant-bound sessions (D11); if ever reachable, the voice path must at least log a capture decision `voice_path_unsupported` |
| E14 | User trashes the diary book | Assistant-aware confirm; distill/capture paused; get-or-create is active-only + detects trashed diary (restore vs. fresh — never silent resurrection/fork); derived-KG dangling handled by the §7 track |
| E15 | Fresh work project, first entry finalize (P2) | Extraction bootstrap at provisioning (§4.1.1 step 4) + "extraction not configured" home-strip state — the save-triggered drainer skips job-less projects silently otherwise |
| E16 | User/agent tries to share or make-public a diary (grant, or sharing-service `visibility=unlisted/public`) | Rejected server-side on **all** paths keyed on `kind='diary'` (D10): both collaborator write handlers + sharing-service `patchSharingPolicy` (via the `kind`-returning access contract). Consumed-by-effect test per path |
| E17 | User/agent tries to convert a diary to another kind (to escape the privacy lock) | Rejected — `kind` is immutable, and leaving `diary` is forbidden (§4.1.2/D10). To get a non-diary book the user creates a new one |
| E18 | Any chapter (diary entry, or a novel draft the writer never publishes) expected in the KG | By design (D15/§4.7): extraction is driven by the indexed-revision pointer, set by "index / add to knowledge" (the diary's "keep entry") — publish not required. A draft that is indexed feeds the KG for **any** kind; an un-indexed draft (or one flagged `kg_exclude`) does not. Publish still indexes (compat) |

## 11. Acceptance (evidence gate)

- **S14 black-box scenario** (S06 discipline + **jargon deny-list check** — success must never require the
  user to operate book/chapter/glossary/entity/draft/publish/inbox vocabulary): a scripted work day →
  capture lands work entities (visible via the home strip, not raw panels) → "End my day" → draft entry with
  correct `entry_date` → user confirms via the review surface → (P2) attributed dated facts in the inbox →
  next-day session answers **"what did <colleague> SAY about <topic> yesterday?"** (the `statement` type,
  not just "decide") via recall. Mid-tier local model. Additional S14 cases: VI-language day ⇒ VI journal;
  stored-injection message must not be followed; quote-yesterday's-entry ⇒ no duplicate capture;
  ≥100-message day reloads with the latest turn visible (desktop + mobile viewport); two-writer concurrent
  send; decisions-per-day ≤ budget.
- Live-smoke ≥2 services per phase (capture chain; distiller write seam; publish→divert-to-inbox chain;
  sharing-policy rejection for journal books).
- Consumed-by-effect tests for every §5 setting, including account-revoke-with-stale-session-override.
- FE Playwright: first-run onboarding intent → provision → chat → home-strip states → review surface,
  desktop + mobile.

## 12. Open questions (PO input wanted)

1. **Trust tiers across ALL three gates** (journal confirm, entity inbox, facts inbox): is per-item gating
   forever, or does an earn-trust auto-accept tier exist (e.g. auto-accept high-confidence entities after N
   consistent approvals)? Touches the LOCKED write-gating law — explicit PO decision. The burden budget
   (≤10/day) is the forcing constraint.
2. **Coach persona defaults:** which 2–3 work-coach templates ship first?
3. **Retention defaults** (P2 track): propose 90-day raw assistant-session retention; journal + KG kept
   until user-deleted — confirm or adjust.
4. **BL-15 amendment wording** for the fifth onboarding intent (P1 needs it).

## 13. Review record (v1 → v2)

5-lens adversarial review, 2026-07-11 (all findings code-verified). P0s and their resolutions:

| Finding | Was | Now |
|---|---|---|
| TEN-1 | D10 guarded only grants; sharing-service unlisted/public PATCH bypassed it | D10 pins visibility + immutable `books.kind='diary'` (v3) + sharing-service `kind` check (named contract change) |
| ARCH-1 | "chat_turn extraction stays disabled" asserted as existing; drainer auto-enables it | Per-source gate = named P2 column consulted in handler + drainer SQL (D6) |
| ARCH-2 | "facts land in the existing inbox" — chain auto-canons; inbox schema can't hold them | Divert-to-inbox mode + pending-facts schema extension + `statement` migration = P2 scope (D4/D5) |
| COST-1 | "daily→weekly→whole-journal rollups for free (md5-cached)" | Daily publish = chapter summary only; rollups = costed P3 deliverable |
| EDGE-1 | E10 claimed consent revocation stops capture; the gate never read the setting | Consent one-home = the project flag the gate already re-reads (D7) |
| EDGE-2 | "GUI all exists" — FE loads first 50 messages, no tail | Tail-first loading = named P1 work item (D12) |
| PUX-1 | "'X said Z' fits the existing fact model, not a schema change" — hard DB CHECK says no | `statement` fact type = explicit migration; S14 tests "say", not just "decide" |

P1-level themes folded in: provisioning idempotency keys + identity propagation (TEN-2/7); consent
narrow-only semantics (TEN-3); complete erasure inventory + memory_forget characterization (TEN-4);
`chat_search_sessions` scope/injection posture + MCP-server infra + trgm index (TEN-5, ARCH-9, EDGE-10);
write seams named (ARCH-3); template binding corrected (TEN-8/ARCH-4); distiller model home + map-reduce +
language (ARCH-5, COST-2, PUX-8); extraction bootstrap (ARCH-6/E15); spend lane as own M item + corrected
envelope incl. tick/compaction/grounding (COST-3/4/5/6/7, D13); timezone deliverable (ARCH-10/EDGE-3);
chapter idempotency mechanism (EDGE-4); session write serialization (EDGE-5); self-feeding mechanism
(EDGE-6); sweep-all-days (EDGE-7); voice hidden in P1 (EDGE-8); journal trash (EDGE-9); assistant-native
review surface + burden budget + week-1 value + C22 intent (PUX-2/3/4/6/7); capture-decision data path
(PUX-5); schema-change inventory corrected (ARCH-8).

**v2 → v3 (PO direction, 2026-07-11):** (1) the one-off `purpose='journal'` marker becomes a first-class
`books.kind` enum (novel/document/lore/diary; `is_bible`→`lore` backfill) — D14, §4.1.2; (2) the diary reuses
the existing book workspace/editor GUI (kind-branched), no new book route; (3) **KG extraction decoupled from
publish, platform-wide** — publish is no longer required to build the KG for *any* kind; extraction is driven
by a per-chapter indexed-revision pointer set by an explicit "index / add to knowledge" action (the diary's
"keep entry"), on drafts or published chapters; publish still indexes (compat). This is a platform change to
the book↔knowledge contract (its own KG staleness sweep — the map showed a naive re-key would conflate the scenes marker) with its own plan —
D15/§4.7. Initially (v3a) scoped to record kinds; widened to all kinds per PO ("writers draft and want KG
without publishing"). (4) the diary publish-block is precisely two things: public sharing/grants hard-blocked
(D10, keyed on immutable `kind`) and the writer "Publish" UI absent — while the finalize→extract trigger is
*retained* under the new index action (the trap: a naive "block publish" would have killed memory-building).
New edges E16–E18. The v2 adversarial fixes above are unchanged.
