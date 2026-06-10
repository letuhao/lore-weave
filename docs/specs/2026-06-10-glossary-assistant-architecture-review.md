# Glossary-Assistant — Architecture Review: Holes & Missing Scenarios

> **Date:** 2026-06-10. **Status:** adversarial review of our own analysis + locked decisions (D1–D13). **Companions:** [`-scenario-coverage.md`](2026-06-10-glossary-assistant-scenario-coverage.md), [`-extended-scenarios.md`](2026-06-10-glossary-assistant-extended-scenarios.md).
> **Purpose:** poke holes — find what the scenario list (S1–S26) and the architecture decisions miss, contradict, or under-scope. Severity-ranked. Findings, not resolutions: items marked **RE-DECIDE** need a user call; **VERIFY** need a spike before the relevant phase.
> **Method:** code-verified where load-bearing (file refs inline).

---

## CRITICAL — DEFECT to repay (not an architecture hole)

### H-A · Kind/attribute scoping was MIS-IMPLEMENTED: the intended 3-tier model collapsed to one global-mutable catalog (VERIFIED + confirmed by owner)

**Finding.** `services/glossary-service/internal/api/kinds_crud.go` gates create/patch/delete kind + attribute with **`requireUserID` only** — no `owner`, no `user_id`, no tenant, no book scoping. Kinds/attributes are a **single global catalog shared across every user and every book**; any logged-in user can rename/delete/restructure a kind that **all other users' books depend on**.

**Root cause (owner, 2026-06-10): this is a CODE DEFECT, not a design hole.** The original, intended design is a **3-tier model**:
1. **System library** — the seeded kinds/attributes; **editable only by the platform owner** (read-only for normal users).
2. **Per-user library** — each user's own kinds/attributes, shared across **that user's** books (enables series/cross-book reuse, S27).
3. **Per-book derived** — per-book selection / override / addition (D8/D9) on top of (1)+(2).

An early AI-agent implementation collapsed (1)+(2) into a single global-mutable catalog (the `requireUserID`-only path). **This is tech debt to repay** — the fix is to implement the scoping that should have existed, not to re-decide anything.

**FIX (folds into Foundational F3).** Introduce the missing tiers:
- **System tier:** lock kind/attribute mutation on the seeded catalog to platform-owner/admin (the rest read it).
- **Per-user tier:** kinds/attributes scoped by `owner_user_id`; a user's customizations live here, never touching system or other users.
- **Per-book tier (D8/D9):** selection/override/addition referencing system+user definitions.
- **S2** "new kind" → lands in the **per-user** library (+ enabled for the book); **S3** "optimize for this book" → **per-book** override on top — neither mutates the system tier or other users.
This **also resolves H-I governance**. **Until repaid, S2/S3 must not be exposed** (they'd mutate shared/system definitions). The repayment is a Foundational prerequisite (see F3, now widened).

---

## HIGH — design must resolve before the relevant phase

### H-B · E0 collaboration blast radius is platform-wide, not glossary-only

`verifyBookOwner` / `owner_user_id` is the guard on **every per-book write endpoint** — across glossary-service *and* book-service *and* (per CLAUDE.md) knowledge/translation. Honoring grants (D7/D10/E0) means updating **all** of them, and the **manual `/v1` UI endpoints too** — not just the assistant tools (else a shared editor can edit via chat but not via UI, or vice-versa: incoherent). E0 is therefore a **cross-service epic touching the entire per-book write surface**, far larger than "extend `checkBookOwnership`." **Action:** before scoping E0, enumerate every `verifyBookOwner` call site across services; decide whether E0 is glossary-first (assistant + glossary UI) or truly platform-wide in one pass (the user chose "platform-wide" — confirm the full service list).

### H-C · Async result delivery into chat is unproven (Path B's "report later") — VERIFY EARLY

suspend/resume is durable (`chat-service/app/db/suspended_runs.py`), but resume is triggered by a **frontend/card action** (the user clicks Apply). There is **no evidence chat-service can inject a server-initiated assistant turn when a background job completes**. If it can't, Path B (D3) degrades from "start job, get notified" to **poll-on-ask** ("is it done yet?"). This silently weakens S7, S8, S5, S15. **Action:** spike "can a job-completion event push a turn/card update into an existing conversation?" **before** committing the Phase-6 async design — don't discover it at build time. If absent, it's its own infra task (server→chat push), possibly part of E0/F5.

### H-D · Stateless confirm-token doesn't fit schema change-sets (Phase 4 + D9)

The P4 path mints a **stateless HMAC token = HMAC(payload)** and creates a **single global** kind/attribute. A change-set (kind + N attributes + edits + removals + **per-book** selections per D9, scoped per H-A) is (a) too large/fragile to encode in one token and (b) must target the per-book layer, not global create. **Likely needs server-side staged-proposal storage** (TTL'd) — which **revisits the "stateless" property** (INV-9/H8 rationale). **Action:** redesign the confirm mechanism for multi-op, book-scoped change-sets; preserve the un-bypassable human gate without relying on token-encodes-everything.

### H-E · Per-book "effective schema" blast radius is under-stated, and its data model is unspecified

D9 means **every schema reader** must switch from "global kind definition" to **"effective schema for book"** = system kind + per-book selections/overrides/additions. That includes: entity-create attribute seeding, the extraction profile, **the `glossary_list_kinds` MCP tool** (today returns the global schema — if the assistant reasons on global while entities seed from effective, it's wrong), and the assistant's reasoning generally. Moreover, **where do per-book attribute overrides/additions live?** No table exists; F3 names `book_kind_selections` for *enablement* but not the **attribute override/addition** model (D9). **Action:** design the per-book schema data model (selection + override + addition tables) and audit/convert *all* schema readers in F3.

---

## MEDIUM

### H-F · Multi-gate-per-turn suspend behavior unverified
S2 (kind + attrs = several confirms) and S19/S12 (batch) may need **multiple suspends in one logical operation**. If one suspend **ends the turn**, a 3-confirmation flow becomes 3 turns — awkward, and the LLM must re-orient each turn. **VERIFY** the run-loop's behavior with sequential gates; may favor a single multi-row card (already the plan for batch) over N single-gates.

### H-G · Injection defense (S24) becomes load-bearing *before* Phase 8, because of E0
S24 was scheduled at web-search (Phase 8). But once **collaboration (E0)** lands, a **malicious shared collaborator** can plant prompt-injection in an entity description / alias that the **owner's** assistant later reads as DATA. INV-6 hardening + injection tests must therefore be validated **when E0/multi-user content arrives**, not deferred to Phase 8. **Action:** pull injection-hardening forward to whenever untrusted *co-author* content first exists.

### H-H · Two translation mechanisms after D2
Aliases move to a first-class table **with a `language` column** (D2), while entity **names and other attributes** keep per-language values in `attribute_translations`. So "translate this entity" (S4) writes `attribute_translations` for the name but the **alias table** for aliases — an asymmetry. **Action:** make this split deliberate and consistent in the S4/S6 tool + card (one review surface spanning both stores), or reconsider whether names+aliases share one model.

### H-I · Global schema has no governance and no revision history (worsened post-E0)
Entities have revisions/restore; **kinds/attributes do not** (S8 noted "no kind-version tracking"). Combined with H-A (anyone edits global), a kind change is **silent, global, irreversible, and unattributed**. Even after H-A's fix (user customizations → per-book), the **system catalog** still needs change-control + an audit trail once it's editable by anyone. **Action:** add kind/attribute revisioning + a governed edit path for the system catalog.

### H-J · `cached_aliases` / dedup coupling is the riskiest part of the D11 hard-cutover
`findEntityByNameOrAlias` (extraction dedup) and the `cached_aliases` column read aliases-as-attribute today. Hard-cutover (D11) must re-point dedup at the new alias table **and** keep extraction's name/alias matching behavior identical (normalization, NFC, tombstones). A regression here silently **creates duplicate entities** on every future extraction. **Action:** golden tests on dedup before/after; this is the single highest-risk file in F2.

---

## MISSING SCENARIOS (S27+)

Categories the original S1–S26 didn't cover:

- **S27 — Import / cross-book / series reuse.** `/export` exists; **import does not**. "Copy/seed glossary from book A → B", "share kinds across a series/collection". Cross-book is a real authoring need and interacts with H-A (book-scoped kinds + a series-sharing story).
- **S28 — Templates / presets.** A curated "Xianxia starter kit" of kinds+attributes (deterministic preset) vs S2's LLM-generated proposal. Faster, predictable onboarding.
- **S29 — Entity disambiguation at chat time.** User says "edit Lin" but three entities are named Lin. **Every** read/edit scenario silently assumes a unique resolve. Needs a disambiguation UX (the assistant asks which one).
- **S30 — Structured filter queries.** "list all antagonist characters with power_level > X", "entities tagged faction:Z". `glossary_search` is semantic; no structured/attribute filter tool for the agent (partially S15).
- **S31 — Entity lifecycle.** `alive` boolean + status exist. "mark X deceased in chapter N", "deprecate this entity" — lifecycle management beyond approve/reject (S12).
- **S32 — Wiki interplay → RESOLVED: OUT OF SCOPE (owner, 2026-06-10).** glossary-service hosts the wiki, but the glossary-assistant **does not touch wiki** — generation/editing of wiki is owned by the `wiki/llm-building` track. Clean boundary; no wiki tools in this campaign.
- **S33 — Provenance / audit (post-E0).** Multi-user → "who changed what, when" matters. Revisions track an actor type; do they track the **user**? Needed once collaborators write.
- **S34 — Abuse / rate-limit / cost runaway.** An assistant (or a malicious collaborator post-E0) issuing many writes / expensive jobs. Per-user/book rate + cost caps (ties to S21).
- **S35 — Observability.** No story for "are the assistant's tools being used / erroring in prod?" — metrics/tracing on MCP tool calls (the rerank work noted metrics are deferred platform-wide).

---

## What holds up well (no change needed)

- **D3 Path B** composes cleanly with the per-call-fresh-client federation (each poll is independent) — modulo H-C (delivery).
- **D4 confirm-card + undo** is sound given recycle-bin/revisions/merge-journal already exist; just generalize the card.
- **D5 glossary-SSOT relationships** matches the documented two-layer pattern.
- **MCP-first + ai-gateway federation** is consistent; new tools slot in without architectural change (naming/namespacing is a design detail, not a hole).

---

## Recommended actions (priority order)

1. **REPAY the kind-scoping defect (H-A)** — implement the intended 3-tier model (system / per-user / per-book); the early AI impl collapsed it to global-mutable. *Blocks S2/S3 safety; widens F3.* **Confirmed by owner — it's debt, not a re-decision.**
2. **Scope E0 with the full cross-service blast radius (H-B)** — enumerate every `verifyBookOwner` site; confirm platform-wide vs glossary-first.
3. **SPIKE async delivery (H-C)** — prove/disprove server-initiated chat turns *before* Phase-6 design.
4. **Design per-book schema data model + effective-schema readers (H-E)** and the **change-set confirm mechanism (H-D)** together — they're the same surface.
5. **Pull injection-hardening forward (H-G)** to E0/multi-user, not Phase 8.
6. **Golden dedup tests for the alias cutover (H-J).**
7. **Decide the wiki boundary (S32)** and fold S27–S35 into the backlog where they fit.
8. Add **kind/attribute revisioning + governance (H-I)** to the schema work.
