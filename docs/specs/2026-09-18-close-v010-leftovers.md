# Spec — Close the v0.1.0 leftovers so the release can ship

- **Date:** 2026-09-18
- **Status:** 📝 **DRAFT — input to CLARIFY.** Not an approved design. CLARIFY, DESIGN and the PO checkpoint still apply.
- **Source idea:** [`docs/ideas/2026-09-18-close-v010-leftovers.md`](../ideas/2026-09-18-close-v010-leftovers.md) (IDEA-001: 29 ideas, 5 sources, scored shortlist)
- **Evidence it builds on:** [`docs/reports/2026-09-13-ship-handover.md`](../reports/2026-09-13-ship-handover.md) · [`docs/plans/2026-09-13-green-honestly.md`](../plans/2026-09-13-green-honestly.md)

## 1. Problem

The v0.1.0 suite is green: **201 passed · 0 failed · 0 skipped**. Six things are still open, and for the
model-dependent ones a single green run proves nothing:

| # | Leftover | Measured state |
|---|---|---|
| L1 | Plan generation (`analyze`) still truncates | **2 of 31** real runs (≈6.5%); the model repeats one whole array item until `max_tokens` |
| L2 | `materialize` string bounds are unproven | 0/10 truncated with the bounds vs 3/17 without (Fisher p ≈ 0.27) |
| L3 | The critic-timeout fix (240s ceiling) could not be re-broken | the original failure needs a cold model load; manual LM Studio control is off limits |
| L4 | A new book gets its knowledge project only when someone opens it | **298** books half-provisioned; doing it at creation appeared to need reversing ratified rule OQ-1 |
| L5 | The critic result is shown twice on one screen | a UX preference; by design (the panel is what a pop-out reads) |
| L6 | The ship decision (AC-7) | the PO's |

## 2. Who it is for

- **The PO**, who needs L1–L4 closed or honestly bounded before deciding L6.
- **Authors** using plan generation (L1, L2), the co-writer critic (L3), and new books (L4).
- **Self-hosters** running local models, where loops and cold loads actually happen.

## 3. Goals

- G1 — The remaining plan-generation truncation is **retried**, not fatal, and the final failure rate is measured on real runs.
- G2 — The critic-timeout fix is **re-broken and restored** under the plan's Rule 1, without manual LM Studio control.
- G3 — Books created through REST get their knowledge project **at creation**, inside OQ-1 as written.
- G4 — Whatever stays open ships with a **Known issues** entry: what it is, who it affects, the workaround.

## 4. Non-goals

- Reversing OQ-1, or minting any token on a user's behalf.
- Making critique asynchronous (202 + poll). It is the right long-term shape, but it's a contract change and isn't needed to ship.
- New sampler controls (DRY, a wider penalty window). Provider support is unverified.
- Backfilling the 298 existing books. Opening a book still provisions it, as today; a backfill is a separate decision.
- Deciding L5 or L6. Both are the PO's.

## 5. Chosen option — the "ship bundle"

### A — Route truncation into the existing regeneration ladder (L1) · score 4.3

**Verified premise.** `plan_forge/propose_llm_async.py` already regenerates a degenerate response up to
2 times, raising `frequency_penalty` (0.8 → up to 1.8) and temperature each time; `llm.py` records this
clearing loops 3/3 at 0.8. But `plan_forge/llm.py`'s `chat()` raises `LLM job unusable: truncated` when
`finish_reason == "length"`, and the ladder's **first** `client.chat(...)` call is outside the loop — so a
truncated loop throws before the ladder sees it. Both arrived in commit `298bd72a9`. The retry exists
and is unreachable for the failure that remains.

**Shape.** On a structured plan-forge step, a truncated job becomes "degenerate → regenerate" through
the existing ladder, instead of a fatal error. The rule that **truncated output must never reach the
repair/salvage path** stays exactly as it is — that guard exists because a repair "succeeds into garbage".
Only the regenerate branch is new to truncation.

**Bite.** Break it: restore today's raise-before-ladder; the truncating runs fail with `LLM job unusable:
truncated`. Restore: they regenerate.

### B — Let the product cause the cold load (L3) · score 4.0

**Verified premise.** LM Studio loads a registered model on first request; during this cycle the 12B
model was loaded on demand by the product's own call, and memory stayed ≥15 GB free.

**Shape.** No product change. The test method changes: register a second chat model that is **not
currently loaded**, set it as the Work's critic, and run `composition-generate` with and without the
240s critique ceiling. The product's own request triggers the cold load — the normal user path, not
manual LM Studio control.

**Bite.** Without the ceiling, the critic card must fail to appear with `Request timed out`; with it, it
must render. If the cold load finishes under 20s anyway, B cannot bite, and a deliberately slow stand-in
provider on the throwaway stack (IDEA-001 idea 16) replaces it.

### C — Provision the knowledge project at book creation, with the author's own bearer (L4) · score 3.6

**Premise corrected during promotion.** IDEA-001 placed this in the gateway. The gateway does **not**
orchestrate `/v1/books`; it proxies it to book-service. But book-service **already** calls
composition-service with the caller's forwarded bearer (`fetchStructureWork` in
`internal/api/book_structure.go`: `GET /v1/composition/books/{id}/work` with `Authorization: <bearer>`).

**Shape.** After book-service's REST create handler commits the book, it calls
`POST /v1/composition/books/{id}/work` with the **incoming** `Authorization` header — the same call the
Studio makes on open, which creates the knowledge project with the caller's own bearer. Best-effort: a
failure is logged and leaves the book in today's state (the Studio still provisions on open).

**Why this matters.** OQ-1 says knowledge auto-provision stays owner-only, and no owner-identity token
is minted. C obeys that literally: it's the owner's request and the owner's bearer, a few milliseconds
earlier. **The PO no longer has to reverse a ratified security decision to close L4.**

### D — Known issues in the release notes (L2, and any residue) · score 3.5

Each open item gets: what it is, who it affects, the workaround. L2 ships as a stated guardrail until
the soak (IDEA-001 idea 11) measures it.

## 6. Rejected alternatives (from the scoring table)

| Option | Score | Why not now |
|---|---|---|
| Overnight soak for L2 | 3.5 | Useful, but it measures a guardrail that costs nothing if wrong — run it after ship |
| Async critique, 202 + poll | 3.3 | Right long-term; a contract change on a live route, not needed once B proves the fix |
| Wider penalty window / DRY | 3.1 | Depends on LM Studio forwarding `dry_*` / `repeat_last_n`, which is unverified |
| RFC 8693 token exchange | 2.8 | Heavier than C and reopens the OQ-1 decision C avoids |
| Internal route trusting `owner_user_id` (former "option A") | — | Superseded by C: it needed an explicit reversal of OQ-1 |

## 7. Invariant notes

- **A** — none; the change stays inside plan-forge, which already owns its anti-loop policy.
- **B** — none; no product change.
- **C** — respects **OQ-1** as written (owner-only, the caller's own bearer, nothing minted). **Language rule:** book-service is Go, and this is a Go change in the service that already makes the sibling call. **Scope:** no new cross-user data flow.
- **D** — none.

## 8. Risks

- **A:** each regeneration is a full, billed generation; the ladder already caps it at 2 extra calls, and that cap stays.
- **A:** a looping step can now take up to three generations of wall time before it fails, instead of one. The run's user-facing timeout must be checked in DESIGN.
- **C:** book creation gains a synchronous downstream call. It must not make creation fail or noticeably slower — best-effort, with a short timeout; the latency budget is to be set in DESIGN.
- **C:** a second provisioning path could race the Studio's `useEnsureWork` on the first open. `/work` is documented as idempotent ("Already a Work → idempotent return"); DESIGN must confirm that it also holds under concurrency.

## 9. Open questions for CLARIFY

1. **MCP `book_create`.** It runs on the internal routes with an acting `user_id` and **no user bearer** — the exact situation OQ-1 was written for. Do MCP-created books stay open-to-provision (today's behaviour), or does this need its own decision?
2. **L5 — the duplicated critic.** Hide the inline critic while the critic panel is docked and visible (the recommendation), or keep both?
3. **The 298 existing books.** Leave them to provision on open (today), or add a backfill that runs on the owner's next sign-in with their own bearer?
4. **L6 — ship.** GO / NO-GO once A–C are proven and D is written.

## 10. Smallest tests (proposed acceptance hints)

| Option | Test | Drop it if |
|---|---|---|
| A | 30 real plan runs through the API with truncation routed to the ladder; count final failures and retries in `llm_jobs` | more than half the retries also truncate, or final failures do not fall below today's 2/31 |
| B | critic set to a registered, unloaded model; `composition-generate` with and without the 240s ceiling | the cold load finishes under 20s — switch to the slow stand-in provider |
| C | create one book via REST, never open it; its knowledge project exists within seconds | the create handler does not have the caller's bearer — fall back to the UI calling `/work` after create |
