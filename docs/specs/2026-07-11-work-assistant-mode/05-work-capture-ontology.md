# 05 · Work Capture & Ontology — detailed design

**Date:** 2026-07-11 · **Phase:** P1 (entities) / P2 (facts) · **Status:** DESIGN · Implements **D4, D5, D6**.
Register: [`RED-TEAM-2026-07-11.md`](RED-TEAM-2026-07-11.md).

---

## Q1. What is captured, and where does it land?

**Live (P1) — entities.** Reuse the shipped canon-capture spine verbatim: cadence gate → LLM extraction →
**human review inbox** (draft + `ai-suggested`) → promote/reject-with-tombstone. Only the *prompt flavor* and
the *ontology* change.

**Batch (P2) — facts.** On **"Keep entry"** (`chapter.kg_indexed`), the entry is extracted with the work
ontology in a **NEW divert-to-inbox mode**: facts land in `knowledge_pending_facts`, **not** as trusted Neo4j
canon. ⚠️ The *existing* chain writes `pending_validation=False` (trusted) — the inbox landing mode is
**net-new P2 work**, not current behavior.

**Never per chat turn (D6).** The gate is **derived and fail-closed**: `NOT is_assistant AND
chat_turn_extraction_enabled`. A stored `DEFAULT true` copy would be fail-**open** on a privacy flag — on the
exact table that already shipped that bug (T7).

## Q2. The ontology is data, not schema (D5) — with one exception

Work kinds — `colleague · project · meeting · decision · task · term · org` — ship as a **System-tier seed**
(read-only; users clone into their per-book tier, per the User Boundaries law), adopted at provisioning via
the existing `adoptBookOntologyCore`. **Verified: no `glossary_entities`/`wiki` column is needed.**

⚠️ Add the seed as a **new ledger chain entry** — editing `0025_seed_*` in place is a **silent no-op on every
already-migrated DB** (the ADD-COLUMN-won't-revisit-default class, for seed data).

**The one real schema exception:** the **`statement`** fact type ("Alice **said** the budget is frozen").
`knowledge_pending_facts.fact_type` is a closed CHECK (`decision · preference · milestone · negation`) — so
the headline promise *"what did Alice say?"* **hits a hard DB constraint**. It needs a CHECK-widen migration
using the idempotent **DROP-then-ADD CONSTRAINT** pattern (not an inline edit), plus the `Literal` updates
across ≥5 sites, plus structured `subject`/`predicate`/`object`/`event_date`/`provenance` columns and a
nullable `session_id` (and the Pydantic model widened in the **same** change, or the LIST endpoint **500s**).

## Q3. The prompt flavor is resolved SERVER-SIDE

`flavorWorkCapture` (new, non-fiction framing — the fiction flavor explicitly *excludes* real people, the
author, and meta-talk, i.e. exactly our payload). Selected in glossary **from the book's `kind`**, via the
extended `getBookAccess` contract — **never a caller-supplied arg** (the caller is a chat session; its inputs
trace to user data). ⚠️ Gate `kind` behind `lvl != GrantNone` or it becomes an existence oracle (T33).

## Q4. 🔴 Two colleagues named "Minh" (T9) — the work domain's most common case is its silent-corruption case

**Verified.** Glossary dedup is `UNIQUE(book_id, kind_id, normalized_name, scope_label)` — but `scope_label`
is author-set, `DEFAULT ''`, and **capture never sets it**. The KG side is worse: `entity_canonical_id` =
`hash(user, project, kind, canonical_name)` — **`scope_label` isn't in it at all** — and
`canonicalize_entity_name` strips honorifics, so *"Master Minh"* and *"Minh"* also collapse.

In a **novel**, same-name collisions are rare and the author notices. In **real work they are the norm** —
every team has two Alexes — and the user has no reason to inspect the graph. Everything the intern says gets
attributed to the PM, silently. An LLM cannot disambiguate "Minh said…" either.

**Guards:**
1. Capture **never auto-merges** onto an existing live same-`(kind, name)` entity.
2. On collision it emits a **disambiguation review item**: *"Is this the same Minh, or someone new?"* — the one
   inbox decision genuinely worth the user's attention.
3. "Someone new" ⇒ set `scope_label` (role/team, LLM-proposed) and mint a **distinct** entity; record a
   `distinct_from` marker so the pair never re-collapses.
4. Seed a **`same_as` / split** path for the inevitable *"these two are actually one person."*
5. **Rename/merge must re-anchor the KG** (T25) — a glossary merge that doesn't re-point `glossary_entity_id`
   splits a person's timeline into two half-people forever. S14: rename a colleague mid-history, then recall
   their full timeline.

## Q5. The user is not a colleague (T-self)

Capture has no notion of *self* — "I told Alice…" would mint **the user** as an entity (possibly twice: "me"
and their name), flooding co-occurrence detectors and becoming the subject of most `statement` facts.
→ **Seed the user's identity entity at provisioning** (from their profile), mark it `is_self`, and **exclude
it from capture candidates and from detectors**.

## Q6. Third-party fact discipline (R7 — see [`09`](09-settings-consent-privacy.md))

`preference` means *"Kai always carries a sword"* → in work, **"Minh always pushes back"**: a durable,
queryable **behavioral trait claim about a real person**, from one person's account.
→ **Forbid `preference`-type facts whose subject is a third-party entity.** Third parties get **stated, dated,
attributed** facts only (the `statement` type). Enforce in `pass2_writer.py`, with a test.
→ Special-category deny-list in the capture prompt (no health/religion/politics/sexuality entities).

## Q7. Capture must be visibly on or visibly off (E4/PUX-5)

The per-turn `CaptureDecision` is **stdout-only and discarded by the caller** today. → **persist/emit it**
(a `chat_sessions.capture_status` record or a stream event) + a read path + the home-strip chip, with a
consumed-by-effect test (*"chip shows fire=false reason=off_cadence after a gated turn"*). Without this, the
"collecting" chip is the **silent-no-op bug this repo has already shipped twice**.

## Q8. Cost

Capture bills at the **session's model** (there is no cheap-tier routing) — ~N/4 calls/day, ~$0.2–0.5/day on
gpt-4o-class, **$0 on local BYOK**. An optional per-user **capture model role** (P2) would let it resolve a
designated cheap model instead of inheriting the interactive one.

## Q9. Acceptance

Work entities land in the inbox with the work ontology · flavor is **not** caller-settable · two same-named
colleagues ⇒ a **disambiguation item**, never a silent merge · the user's own name is never captured · a
`preference` fact about a colleague is **rejected** · consent off mid-day ⇒ next tick logs `consent_off`, no
capture call · the home strip shows capture true/false **with a reason**.
