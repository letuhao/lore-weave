# IDEA-001 — Close the v0.1.0 leftovers so we can ship

| Field | Value |
|---|---|
| Id | IDEA-001 |
| Status | promoted |
| Recorded | 2026-09-18 |
| Last updated | 2026-09-18 |
| Proposed by | PO, in chat ("help me make idea to fix all leftover, so we can ship") |
| Related | `docs/reports/2026-09-13-ship-handover.md` (the leftovers, measured); `docs/plans/2026-09-13-green-honestly.md` (rows F8, F11, H1, #274); `services/composition-service/app/engine/plan_forge/llm.py` and `propose_llm_async.py` (the existing anti-loop work) |

## Frame

**How might we** close — or honestly bound — every leftover from the v0.1.0 test cycle, so the
release can ship with nothing unexplained?

- **For whom:** the PO making the ship call; authors who use plan generation, the co-writer's critic, and new books.
- **Pain / opportunity:** the suite is green (201 passed · 0 failed · 0 skipped), but six things are
  open, and a green run does not prove the model-dependent ones:
  1. plan generation still truncates about **1 in 15** real runs — the model repeats a whole array item;
  2. the second plan step's string bounds are shipped but **unproven** (p ≈ 0.27);
  3. the critic-timeout fix could not be **re-broken**, because that needs a cold model load and manual LM Studio control is off limits;
  4. a new book gets its knowledge project only when someone **opens** it (298 books are half-provisioned), and doing it at creation seemed to require reversing a ratified owner-only rule (OQ-1);
  5. the critic result is **shown twice** on one screen;
  6. the **ship decision** itself.
- **Already exists?** Yes, and it matters:
  - `plan_forge/propose_llm_async.py` already has a **regeneration ladder** — up to 2 retries with a rising
    `frequency_penalty` and temperature — built for exactly this failure.
  - But `plan_forge/llm.py` raises `LLM job unusable: truncated` inside `chat()`, on the **first** call,
    before the ladder ever sees the content. A truncated loop therefore never reaches the retry. Both
    arrived in the same commit (`298bd72a9`). The retry exists and is unreachable for the failure that is left.
  - `llm.py`'s own notes record that `maxItems` "did nothing" — *for the loop inside one string*. The loop
    that remains is a different mode: one array item repeated 168 times.
  - The composition route already has an async 202 + poll pattern (`_resolveJob` on the frontend) used by sibling LLM calls.
  - `/work` already creates the knowledge project with the **caller's own bearer** — the path OQ-1 permits.

## Diverge

Raw ideas, unjudged, grouped only by which leftover prompted them.

**Plan generation still truncates (1)**

1. **Route truncation into the existing regeneration ladder** — treat `finish_reason=length` on a structured step as "degenerate → regenerate with a higher penalty", not as a fatal error. *(SCAMPER: adapt — reuse what is built)*
2. **Measured `maxItems`** on `arcs`, `events`, `characters` (e.g. 3× the largest real document), run under the same controlled A/B as the string caps. *(constraint forcing)*
3. **Widen the penalty window.** llama.cpp's repeat and frequency penalties only look back 64 tokens by default; the repeated arc object is wider than that, so the penalty never sees the loop. Send a larger window. *(from research)*
4. **DRY sampling** — a sampler built for verbatim loops, with sequence breakers so JSON punctuation can still repeat. *(from research)*
5. **Stream-side loop detector** — watch the stream; when the same 40-token span repeats 3 times, cancel and regenerate instead of waiting for 12,000 tokens. *(analogy: circuit breaker)*
6. **Split analyze into smaller calls** — one per document section or arc; short outputs cannot loop for long. *(constraint forcing)*
7. **Rules first, LLM to fill gaps** — parse the author's headings deterministically, let the model only enrich. *(inversion: what if the model did less?)*
8. **Salvage by dedupe** — stream-parse the partial JSON and keep the unique items before the loop started. *(worst possible idea — "use the broken output")*
9. **A tiny "referee" model** watching the drafter's stream and stopping it when it repeats. *(wild)*
10. **Cloud fallback** — when the local model loops twice, retry the step once on a cloud model the user has registered. *(wild; remove the local-only constraint)*

**The second step's guard is unproven (2)**

11. **Overnight soak** — 200 real plan runs while the machine is idle, both arms, to get a real rate. *(time shift)*
12. **Replay corpus** — save the analyze outputs that fed looping materialize runs, and replay exactly those; the loop depends on the input, so use the inputs that loop. *(steal from workarounds)*
13. **Accept it as a guardrail** and say so in the release notes; prove it after release. *(remove the "must prove before ship" constraint)*

**The critic fix could not be re-broken (3)**

14. **Make critique async (202 + poll)** like its sibling routes — the timeout class disappears, so there is nothing to re-break. *(from research)*
15. **Let the product cause the cold load** — point the work's critic at a registered model that is not loaded; the product's own request makes LM Studio load it. No manual LM Studio control. *(inversion: stop avoiding the condition, trigger it the legitimate way)*
16. **A slow fake provider** — an OpenAI-compatible stub on the throwaway stack that sleeps 30s, registered as the critic. *(analogy: test double)*
17. **Pre-warm the critic model** when the compose panel opens. *(persona: the author who hates waiting)*
18. **Show "the critic is still reading"** instead of an error while it works. *(persona)*

**Knowledge project at creation (4)**

19. **OAuth 2.0 token exchange (RFC 8693)** — the auth service mints a short, delegated token carrying an `act` claim that names the acting service. *(from research)*
20. **Internal route that trusts `owner_user_id`** from the event, with a service token and an audit row — the option already on the table. *(the earlier "option A")*
21. **The UI calls `/work` right after it creates a book** — the author is present with their own bearer at that moment. *(remove the "must be backend" constraint)*
22. **The gateway orchestrates creation** — the book-create request already carries the user's bearer; the gateway creates the book, then calls `/work` with that same bearer. Server-side, every REST client, and within OQ-1 as written. *(SCAMPER: combine)*
23. **Backfill the 298** the next time each owner signs in, using their bearer. *(steal from workarounds)*
24. **Merge the knowledge project into the book** so there is nothing separate to provision. *(wild)*

**Critic shown twice (5)**

25. **Hide the inline critic while the critic panel is docked and visible.** *(eliminate)*
26. **Keep both, but make the panel a summary** — the inline card is the working view. *(modify)*

**The ship decision (6)**

27. **Ship with a "Known issues" section** — what, who it affects, and the workaround. *(from research)*
28. **Label plan generation "beta"** in the UI for v0.1.0. *(modify)*
29. **Ship now and fix forward on a fixed weekly cadence.** *(wild)*

## Research

| Source | What it shows | Read |
|---|---|---|
| [llama.cpp — completion tool README](https://github.com/ggml-org/llama.cpp/blob/master/tools/completion/README.md) | DRY sampling exists for verbatim loops (`dry-multiplier` 0.8, `dry-base` 1.75, `dry-allowed-length` 2, `dry-penalty-last-n` 64 suggested); default sequence breakers include `\n`, `:`, `"`, `*`; the ordinary repeat/frequency penalty window (`repeat-last-n`) defaults to **64 tokens** | 2026-09-18 |
| [Sampling args in llama-server (A. Ewerlöf)](https://blog.alexewerlof.com/p/sampling-args-in-llama-server) | search result: models get "stuck in an unrecoverable repetition loop" on structured formatting; sequence breakers let structural characters repeat while text may not | 2026-09-18 (search snippet only — *not fetched*) |
| [Azure Architecture Center — Asynchronous Request-Reply](https://learn.microsoft.com/en-us/azure/architecture/patterns/asynchronous-request-reply) | 202 + `Location` + `Retry-After`; a status resource with `status`/`createdAt`/`lastUpdatedAt`; 303 to the result; idempotency key; recommended when the back end takes seconds to minutes | 2026-09-18 |
| [RFC 8693 — OAuth 2.0 Token Exchange](https://datatracker.ietf.org/doc/html/rfc8693) | delegation (the actor keeps its own identity, recorded in the `act` claim) vs impersonation (the actor becomes indistinguishable from the user); the STS must decide *which* clients may receive delegations — the security weight sits there | 2026-09-18 |
| [Release notes best practices — search results (AnnounceKit, Featurebase, ReleasePad)](https://announcekit.app/guides/release-notes-best-practices) | a known issue should say what it is, who it affects, and the workaround; "silence doesn't hide a bug people are already hitting" | 2026-09-18 (search snippets) |

- **What users say:** for local models, repetition loops on structured output are a known, common complaint; the standard advice is DRY or a wider penalty window, not a grammar change. *(search snippets; not a user study)*
- **What failed:** the repo's own record — `maxItems` failed against the *in-string* loop (right lever, wrong mode); a repair prompt "succeeds into garbage" on a loop, which is why the ladder regenerates instead.
- **Unverified:** whether LM Studio's OpenAI-compatible endpoint accepts `dry_*` or `repeat_last_n` fields. Nothing here confirms it — ideas 3 and 4 depend on it.
- **Ideas added from research:** 3, 4, 14, 19, 27.
- **Deliberately not followed:** one DRY documentation site answered with an "authentication" flow instead of content; treated as untrusted and ignored.

## Converge

**Clusters:** (a) make the loop recoverable — 1, 5, 8, 10; (b) make the loop rarer — 2, 3, 4, 6, 7, 9;
(c) get proof without forbidden steps — 11, 12, 15, 16; (d) remove the timeout class — 14, 17, 18;
(e) provision at creation within OQ-1 — 21, 22, 23; or by changing OQ-1 — 19, 20, 24; (f) ship honestly — 13, 27, 28, 29.

| # | Candidate | Value | Fit | Effort | Risk | Evidence | Novelty | Score |
|---|---|---|---|---|---|---|---|---|
| A | **Route truncation into the regeneration ladder** (1) | 5 — turns the remaining 1-in-15 hard failure into a retry that already clears most loops | 4 — reuses built, measured code | 5 — one branch where the error is raised | 4 — bounded at 2 extra billed calls, already the ladder's limit | 4 — the ladder measured 3/3 at penalty 0.8; truncation observed 2/31 | 2 — the plan already intended it | **4.3** |
| B | **Let the product cause the cold load** (15) | 4 — closes the one fix that could not be re-broken | 3 — a test-method change, no product change | 5 — register a model, point the critic at it | 5 — no manual LM Studio control, no memory beyond what already fits | 3 — LM Studio loads on demand (observed); cold-load timing not yet measured | 3 | **4.0** |
| C | **Gateway orchestrates create → `/work` with the user's bearer** (22) | 4 — stops new half-provisioned books for every REST client | 4 — **stays inside OQ-1** (owner-only, the caller's own bearer, no minted token) | 3 — one orchestration step plus the MCP `book_create` path | 4 — no new trust boundary; a failure degrades to today's behaviour (Studio still provisions on open) | 3 — `/work` already does this with the caller's bearer | 3 | **3.6** |
| D | **Ship with a Known issues section** (27) | 4 — the PO gets a clear, honest release; users get workarounds | 3 | 5 | 3 — ships known defects, stated | 4 — consistent across sources | 1 | **3.5** |
| E | **Overnight soak for the unproven guard** (11) | 3 — turns p ≈ 0.27 into a real number | 3 | 4 — a script that already exists (the probe) | 5 — read-only, throwaway stack | 3 | 2 | **3.5** |
| F | **Async critique, 202 + poll** (14) | 4 — the whole timeout class goes away | 4 — matches sibling routes | 2 — backend job + frontend polling | 3 — contract change on a live route | 4 — standard pattern, well documented | 2 | **3.3** |
| G | **Wider penalty window / DRY** (3, 4) | 3 — may make the loop rarer | 3 | 4 — request fields only, *if* forwarded | 3 — unverified support; may disturb JSON keys | 2 — LM Studio support unverified | 3 | **3.1** |
| H | **RFC 8693 token exchange** (19) | 4 | 3 | 1 — needs an STS inside auth-service | 2 — a new delegation surface | 4 — a standard | 3 | **2.8** |

**Invariant notes:**
- **A** — none. The anti-loop measurements already live in `llm.py`; the change sits in the plan-forge engine, not the agent path.
- **C** — respects OQ-1 as written: the owner's own bearer creates the project, and no token is minted. **This removes the need to ask the PO to reverse a ratified security decision.** It must also cover the MCP `book_create` path, or MCP-created books stay half-provisioned (degrading to today's behaviour, not worse).
- **H** — conflicts with the spirit of OQ-1 ("rather than minting an owner-identity token"); a delegated token with `act` is a narrower form, but it is the same decision.
- **F** — a contract change on a route a live UI calls; needs its own CLARIFY.

**Recommendation — the "ship bundle":** **A + B + C**, then **D** for whatever is still open.

- **A** is the highest-value, lowest-effort move in the list: the fix for the remaining failure was built, measured, and made unreachable by a guard added in the same commit. Wiring it in is a one-branch change with a bite already available (the truncating runs).
- **B** closes the only fix that could not be re-broken, without breaking the "no manual LM Studio control" rule — the product loads the model, as it would for any user.
- **C** replaces the H1 question. The PO no longer has to decide whether to reverse OQ-1, because the creation path can use the same owner bearer the Studio already uses.
- **D** covers the residue honestly (for example, the step-2 guard until E runs).

**Why the others lost:**
- **F** is the right long-term shape, but it is a contract change, and A–C already close the release gaps.
- **G** depends on unverified provider support. Worth a spike after release.
- **H** is heavier than C and re-opens the decision C avoids.
- **E** is good but not blocking: it measures a guardrail that costs nothing if wrong. Run it after ship.
- **Critic shown twice (25, 26)** is not scored: it is a UX preference with no defect behind it. **Recommend 25 (hide inline while the panel is docked)**, as the PO's call.

## Shortlist

- **shortlisted — A:** route `finish_reason=length` on structured plan-forge steps into the existing regeneration ladder.
- **shortlisted — B:** reproduce the critic's cold load through the product (critic set to a registered, unloaded model).
- **shortlisted — C:** gateway orchestrates book creation → `/work` with the caller's bearer (and the MCP `book_create` path).

## Smallest test

- **A — test:** run 30 real plan runs through the API with truncation routed to the ladder, and count final failures and retries from `llm_jobs`.
  **We drop the idea if:** more than half of the retries also truncate, or the final failure rate does not fall below today's 2/31.
- **B — test:** register a second chat model that is not currently loaded, set it as the work's critic, and run the composition-generate spec with and without the 240s critique ceiling.
  **We drop the idea if:** the cold load finishes under 20s anyway. In that case the original failure needs a slower condition, and idea 16 (slow fake provider) replaces B.
- **C — test:** create one book through the API and one through MCP, never open them, then check that both have a knowledge project within seconds.
  **We drop the idea if:** the gateway does not see the user's bearer on book creation. Then idea 21 (the UI calls `/work`) is the fallback.

## Log

- 2026-09-18 — seed — PO request in chat: ideas to fix all leftovers so v0.1.0 can ship
- 2026-09-18 — explored — /ideate session: 29 ideas from 9 techniques plus research, 5 sources read (2 from search snippets only)
- 2026-09-18 — shortlisted — A (4.3), B (4.0), C (3.6) as the ship bundle; D (3.5) for the residue
- 2026-09-18 — promoted — docs/specs/2026-09-18-close-v010-leftovers.md (draft for CLARIFY). Premise corrected on promotion: C lives in book-service's REST create handler, which already forwards the caller's bearer to composition — not in the gateway, which only proxies `/v1/books`.
