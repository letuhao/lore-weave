# 09 · Settings, Consent, Privacy & Erasure — detailed design

**Date:** 2026-07-11 · **Phase:** P1 (settings, consent, **egress guards**) / P2 (erasure, retention) ·
**Status:** DESIGN — written *after* the red team, so it owns its findings rather than inheriting them.
Implements **D6, D7, D9, D10, D16, D17, D18**. Register: [`RED-TEAM-2026-07-11.md`](RED-TEAM-2026-07-11.md).

> **This doc carries the feature's highest-severity work.** The red team's P0s were not mostly *bugs* — they
> were **missing privacy machinery**. Two of them are live platform holes today, independent of the assistant.

---

## Q1. What is actually private here, and from whom?

Three different adversaries, and the design only ever defended against the first:

| Adversary | Defended today? | Answer |
|---|---|---|
| **Another user** | ✅ Yes — tenancy law, per-user scope keys, grant checks. The red team could not break it. | Holds |
| **The internet / a third-party agent** | ❌ **No** — 5 of 7 egress paths were unguarded (§Q2) | **D16 taint** |
| **The operator** (the person who runs the server) | ❌ **No — and this is the likeliest adversary for a *work* assistant** | §Q6 — honest disclosure now; envelope encryption designed now, built later |

**The uncomfortable truth (T19):** "self-hosted ≠ single-user" is locked law here. Its **corollary is
unstated**: *"private" means private from other **users**, not from the **operator**.* An admin with DB
access reads every diary. And the most likely deployment of a work assistant is **one the employer controls**
— while the feature's entire value proposition is candor about your boss, your job hunt, your frustrations.
**We must not make privacy promises in onboarding copy that the architecture cannot keep.**

---

## Q2. The egress surface — D10 guarded 2 of 7 (D16)

A diary row's privacy was enforced on `books`. **Everything downstream of `books` is a separate egress with
its own rules**, and the red team walked out through five of them.

| # | Path | Status | Guard (each with a consumed-by-effect test) |
|---|---|---|---|
| 1 | Collaborator grants | ✅ guarded | both write handlers reject `kind='diary'` |
| 2 | sharing-service `patchSharingPolicy` | ✅ guarded | **live** kind lookup per PATCH (it serves from a cached policy row otherwise, so a pre-existing row would bypass a create-time check) |
| 3 | **The wiki** 🔴 | ❌ **wide open** | see §Q3 — four sub-guards |
| 4 | **Public MCP gateway** 🔴 | ❌ **wide open** | see §Q4 |
| 5 | **`memory_*` all-projects fallback** 🔴 | ❌ **leaks into other sessions** | see §Q5 |
| 6 | Notifications | ❌ unguarded | diary-sourced notifications are **content-free** ("You have an unfinished entry"). Never quote the diary into a push/email — it lands on a lock screen or an **employer-hosted inbox** |
| 7 | Library/catalog listings + export | ❌ unguarded | the diary is **hidden from the default library grid** (the `is_bible` hiding precedent); export is owner-only and designed (§Q8) |

### D16 — the rule (locked)

> A row **derived from** a `kind='diary'` source is **diary-tainted**. Diary-tainted rows are excluded from
> **every** list · search · export · notification · public-MCP surface **unless the caller is the owner in an
> assistant context**.

Taint propagates to: KG facts/entities, glossary entities, wiki articles, entity enrichments, notification
bodies, library/catalog listings, statistics. **Enforce on LIST/SEARCH, not only per-resource** — the repo's
own *"per-resource misses LIST"* lesson is exactly this bug.

---

## Q3. 🔴 The wiki — it would auto-publish AI biographies of real colleagues

**Verified.** The public wiki gate reads **`books.wiki_settings.visibility == "public"`**
(wiki_handler.go:1459) — a **JSONB blob PATCHable on the book** (`PATCH /v1/books/:id`, server.go:887-893),
keyed on **nothing about `kind`**. Sharing-service's guard never runs on this path. `wiki_articles` is **one
article per entity** (`UNIQUE(entity_id)`); `generateWikiStubs` **auto-writes prose** from the KG (revision
summary: *"Auto-generated from KG"*); unauthenticated readers can list and read; `community_mode` lets **the
public submit edit suggestions**. A second engine, `entity_enrichments`, manufactures confidence-scored
AI-authored "dimensions" about an entity.

**Because D14 reuses the book GUI**, the diary user gets a one-click path to: generate an **AI-written
biography of every colleague in their diary** → flip `wiki_settings.visibility='public'` → serve those
biographies **to the open internet** → open them to public edit suggestions. A real person, profiled and
published, who never consented and does not know the store exists.

**Guards (all four, defense in depth — the flag is a legacy JSONB blob; assume drift):**
1. `PATCH /v1/books/:id` **rejects any `wiki_settings` mutation** on `kind='diary'`.
2. `generateWikiStubs` **rejects** diary books.
3. `entity_enrichments` proposal **rejects** diary books.
4. `checkWikiPublic` **fails closed** on `kind='diary'` even if the flag somehow got set.
5. **Entity-level guard (D16/R6):** entities can be merged, moved, or referenced from a non-diary book — so
   mark real people (`kind='colleague'` / a `third_party` predicate) and **block wiki + enrichment + share at
   the entity level**, not only the book level.

**Third-party fact discipline (R7):** `preference` facts mean *"Kai always carries a sword"* → in work that
becomes **"Minh always pushes back"**: a durable, queryable **behavioral trait claim about a real person**,
from one person's account. **Forbid `preference`-type facts whose subject is a third-party entity**; restrict
them to `statement` (what the user reports X said, on a date). Enforce in `pass2_writer.py`, with a test.

---

## Q4. 🔴 The public MCP gateway — scoped by domain, never by resource

**Verified.** A key with `domain:book` + `domain:knowledge` reads the entire diary and work KG, and can
**write**:

- `kg_project_list` (`read`) → enumerate the assistant project id.
- `memory_search` / `memory_recall_entity` / `memory_timeline` (`read`) — **`project_id` is a caller-supplied
  arg** → query the diary KG directly.
- `book_list` / `book_get_chapter` / `book_list_revisions` (`read`) → **read the diary entries verbatim**.
- `glossary_search` / `story_search` → the captured colleagues, full-text.
- `book_chapter_save_draft`, `memory_remember`, `memory_forget` are **`write_auto`**.

The whole design was *"the diary is private because it's un-shareable."* An external agent with a legitimate
**book-domain** key silently inherits it — and it is third-party data.

**Guards:**
1. **A public key never resolves a `kind='diary'` book**, and `book_list` / `kg_project_list` /
   `story_search` / `glossary_search` **filter diary rows out of LIST results** (D16).
2. An explicit opt-in scope **`domain:diary`** that **no key gets by default** and that the key-mint UI marks
   as dangerous.
3. The new `book_chapter_index_knowledge` tool is added to `TOOL_POLICY` **deliberately** (absence = deny,
   which is the right default — make it a decision, not an accident).
4. Add a **public-MCP path** to D10's "consumed-by-effect test per share path" list.

---

## Q5. 🔴 `memory_*` leaks the diary into other sessions

**Verified.** `memory_recall_entity` / `memory_timeline` pass `project_id=None` when a session has no linked
project, and the Cypher idiom is `($project_id IS NULL OR x.project_id = $project_id)` → **ALL of the user's
projects**. `_GET_ENTITY_WITH_RELATIONS_CYPHER` has **no project filter at all** (always user-wide).
`memory_forget` is user-wide by construction.

→ A **novel-writing** session with no project linked will surface the user's **colleagues and work
decisions**. It is also an exfil path when combined with Q4.

**Guards:** `memory_*` must **require an explicit project scope** for diary-tainted data (never the
all-projects fallback); `get_entity_with_relations` gains a project filter. Test: a non-assistant session
must return **zero** diary entities.

---

## Q6. Consent, egress disclosure, and the settings surface

**D7 — consent has ONE home:** the work project's `canon_capture_enabled` — the flag the per-turn gate
already re-reads every turn. Default **off**; fail closed. A session may only **narrow** (pause), never widen.

**D6 — the extraction gate is DERIVED and fails closed:** `NOT is_assistant AND chat_turn_extraction_enabled`.
Never a storable `DEFAULT true` copy (v2's version was **fail-open on a privacy flag**, on the exact table
that already shipped this bug — T7).

### 🔴 T8 — D4 gates the WRITE, not the SEND

"Every unattended write is draft-into-inbox" governs where **rows land**. It says nothing about **what is
sent to an LLM provider**. Capture is fire-and-forget with **no pre-send gate**; the same day's text is sent
again to the distiller, and a third time to extraction. MNPI, privileged, or PHI content is **at the provider
before any inbox exists**.

**Worse:** `assistant.distill_model` falls back to *the account's chat default*. A user who deliberately
chose a **local** model for the assistant session can have their **entire day's transcript shipped to a cloud
provider** at distill time. Nothing discloses this.

**Guards:**
1. **A per-turn "don't remember this" control.** The mechanism half-exists — `should_capture` already returns
   `grounding_disabled` and skips capture when grounding is off for a turn. Promote it to a **visible privacy
   affordance** — **and wire the same flag into the distiller**, which today reads the whole day regardless
   (so the existing escape hatch leaks).
2. **Egress disclosure in settings:** *"Your diary will be sent to **&lt;provider&gt;** for distillation"* —
   with effective value + source tier (the TierChip contract §5 already requires). A distill model on a
   **different provider** than the session model requires **explicit confirm**, never a silent cascade fallback.
3. **Ephemeral / `no_persist` mode** for regulated users; a "sensitive content detected — remember this?"
   confirm on high-signal shapes (deal names, case numbers, PHI).

### Settings table

| Setting | Home / tier | Default | Notes |
|---|---|---|---|
| `assistant.enabled` | Account (`user_chat_ai_prefs.assistant` JSONB) | off | |
| **Capture consent** | **`knowledge_projects.canon_capture_enabled`** — the ONE home (D7) | **off** | fail-closed; session may only narrow |
| `assistant.distill_enabled` | Account | off | spend-causing |
| `assistant.distill_model` | Account (ModelRole cascade) | unset → chat default → **visible failure** | **cross-provider fallback ⇒ explicit confirm** |
| **`assistant.coaching_enabled`** | Account | **off** | it spends tokens **and it judges a person** — off is the only defensible default |
| `assistant.spend_cap_usd` | Account | platform default | §Q7 |
| `user.timezone` (IANA) + `day_cutoff` | Account — **auth-service `user_preferences`** (platform-wide fact) | unset ⇒ UTC + warning; auto-distill held | `chat_messages.local_date` stamped at **write** time |
| `ASSISTANT_MODE_ENABLED` | Deploy env | on | **ceiling only** |

All consumed-by-effect (tests assert behavior); effective value + source tier surfaced.

---

## Q7. Spend exhaustion — the degrade ladder (T22)

For an all-day companion, **the failure mode is the product.** "Guardrails exist" is not a design. When the
cap is hit at 2pm:

1. **Background streams stop first** — capture, distill, extraction. The home strip says
   *"Memory paused — daily cap reached"* with the reason and a top-up action.
2. **Foreground chat keeps working** on the user's main budget (different lane, different consent).
3. **The undistilled day is queued, not lost** — it distills at the next window.
4. **Never a silent no-op.** "Cap exhausted mid-day" is an S14 scenario.

---

## Q8. Erasure — unbuilt infrastructure (D18)

See [`01-data-architecture.md`](01-data-architecture.md) §8 for the verified detail. The two foundational facts:

- **Chapters are never row-deleted** (soft `purge_pending`; **no purge worker exists**) → every
  `ON DELETE CASCADE` in the copy-set is **inert**; the diary text survives forever in
  `chapter_revisions`/`drafts`/`raw_objects`/`blocks`.
- **Neo4j facts survive at `evidence_count=0`** with content **and embeddings** — and `merge_fact`'s natural
  key means a later mention **resurrects** them. *Invisible is not erased.*

**Deliverables:** a **purge worker**; an **erasure job** (`remove_evidence_for_natural_key` **then**
`cleanup_zero_evidence_nodes`, under the project lock); day-scoped deletes for summaries,
`extraction_leaves(+raw)`, pending facts, glossary drafts, `compact_summary`, glossary `evidences`,
**`usage_logs` (they hold the decryptable prompt text = the diary)**, and **MinIO objects**; coach transcripts
+ scorecards + `reflection_patterns` added to the inventory.

**Three verbs the user actually needs** — all D17's one three-legged write (*amend PG SSOT → re-index →
reconcile graph*):

| Verb | Today | Needed |
|---|---|---|
| **Correct a memory** ("Alice said that, not Minh") | ❌ nothing. `memory_forget` never touches PG → the entry still says Minh, and a rebuild resurrects the fact | amend the entry revision → `chapter.kg_indexed` → invalidate the superseded fact |
| **Forget a person** (a colleague asks to be removed) | ❌ nothing. Erasure is day-scoped; **entity-delete → KG has no cascade and no event type at all** | cascade glossary entity + KG entity + facts/evidence/passages/embeddings + pending facts, **and redact the diary spans that name them** |
| **Delete my day** | ❌ inert (Q8 above) | purge worker + erasure job |

**Backups (T23):** a restore **resurrects erased days** (14-day retention). Ship an append-only **erasure
log** replayed after any PITR/restore, and state an honest *"erasure completes within N days"* promise that
matches backup retention.

---

## Q9. Special-category and third-party data

- **Personal/health content will land in a work diary** ("my dad's in the hospital"; "therapy at 4"). That is
  GDPR **Art. 9** special-category data. → a **"personal aside" classification** at distill: kept in the entry
  as the user's own record if they want it, but **excluded from the KG and from coaching detectors** by
  default; a special-category **deny-list in the capture prompt** (no health/religion/politics/sexuality
  entities).
- **Affect inference (T36):** *"you mentioned 'anxious' 4 of 5 days"* honors the letter of the honesty
  constraint while being, in effect, a **mental-health inference**. The deny-list must live **in the
  detector** (code), not in the phrasing prompt.
- **Employment epoch (T18):** on a job change the KG otherwise blends the ex-employer's confidential facts
  into the new job. Close the epoch (facts get `valid_until`), start a fresh project + diary volume, default
  recall to the **current** epoch, and offer **export-then-purge** at the boundary — which is also the feature
  that makes the product *trustworthy to leave a job with*.

## Q10. Phasing

| Phase | Scope |
|---|---|
| **P1** | Settings category; consent one-home (D7); derived fail-closed extraction gate (D6); **ALL egress guards (D16 — Q2/Q3/Q4/Q5)**; egress disclosure + per-turn "don't remember this" (T8); `coaching_enabled` off; timezone + `local_date` |
| **P2** | Erasure (D18: purge worker + erasure job + the corrected copy-set); D17 memory amendment (correct / forget-person); retention windows; spend degrade ladder; employment epoch; special-category handling |
| **P3+** | Per-user envelope encryption for diary content (design **now** — it constrains the KG/embedding schema) |

## Q11. Open decisions

1. **Operator disclosure copy** — derived from actual deployment facts ("Your administrator can access this
   data" / "You are the administrator"). Who writes it, and does it gate provisioning?
2. **Envelope encryption**: how much does it break KG/embedding search? Scope now, decide before P3.
3. Retention defaults (proposed: 90-day raw assistant sessions; diary + KG until user-deleted).
4. Do the **wiki + public-MCP guards ship as their own fix track** (they are live holes today, independent of
   this feature)?
