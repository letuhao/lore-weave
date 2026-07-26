# S02 · "Add my characters and terms to the book" — the job that keeps failing

> Anchor scenario, written **black-box** (from a user who doesn't know the platform). It reproduces the
> single most-cited failure: the assistant spins on searching and never adds anything. Getting a
> clueless user through this with gemma is the north star for the whole effort.

| Field | Value |
|---|---|
| **Scenario id** | S02 |
| **Maps to umbrella workflow** | W3 / W2 — [`../2026-07-09-agent-discoverability-and-workflow-architecture.md`](../2026-07-09-agent-discoverability-and-workflow-architecture.md) §5 (builder hint only) |
| **Persona** | P2 Linh (worldbuilder) / P1 Mai (author) — but assume near-zero platform knowledge |
| **Surface** | the chat, open next to my book |
| **Model under test** | `gemma-4-26b-a4b-qat` |
| **Fixture** | book Mị Đế + a short notes doc listing my cast, techniques, and terms |
| **Status** | 🔬 baseline pending |
| **Owner** | this session |

## 1. Who I am (the unknown user)

- **Mental model:** I'm writing a xianxia web-novel. I have a notes file with my characters, sects,
  techniques, and special terms. I think of the assistant as "the helper in my book" — I expect I can
  just tell it about my world and it remembers/records it. I've never read any docs.
- **The words I use:** "add", "remember", "put these in", "my characters", "my terms", "here's my notes".
- **Words I do NOT know (must never be required of me):** *entity, glossary, kind, attribute, ontology,
  extraction, propose, confirm-token, tool, draft status.* I will not type any of these. If getting my
  stuff recorded *requires* me to know one, the scenario has failed.

## 2. What I'm trying to get done

I want the people, places, and terms from my notes recorded in the book so the assistant knows about
them later. That's it. I don't care how it's stored.

## 3. What I have / where I'm starting

- I'm in my book Mị Đế, chat open.
- I have a short notes doc I can paste (a handful of characters with a line of description each, a couple
  of techniques, a couple of terms).
- I might instead just type a couple of them by hand.

## 4. What I do and what I expect to see

### Path A — I just tell it a couple

| # | I say / do | I expect to see |
|---|---|---|
| 1 | "Add these to my book: a character called Lâm Uyên, a young sect heir. And a term 'Chân Linh' — it means the core life-essence." | It understands, records them, and tells me it did — ideally showing me what it saved. Not a wall of questions, not "searching…", not "I can't". |
| 2 | "Show me Lâm Uyên." | It shows Lâm Uyên with the description I gave. Proof it stuck. |

### Path B — I paste my notes

| # | I say / do | I expect to see |
|---|---|---|
| 1 | (paste notes doc) "Add everyone and everything in here to my book." | It reads my notes, tells me what it found ("6 characters, 2 techniques, 3 terms"), and records them — maybe asking me to confirm the batch once. |
| 2 | "Did you get them all? Any duplicates?" | An honest count of what it added and anything it skipped as already-there. |

## 5. How I'll know it worked — and how I'll know it failed

- **Worked (I can check myself):** I ask to see my characters/terms and they're there, with the
  descriptions I gave. From the notes-doc path, roughly the count I pasted shows up.
- **Failed (what I'd actually experience):**
  - It keeps saying "let me search for the right tool…" / "searching…" and **nothing gets added** (the
    reported failure).
  - It tells me it **can't add characters** to my book (it can — this is the exact "weaker model couldn't
    add entities" bug).
  - It asks me to pick a "kind" or name some feature I've never heard of before it'll do anything.
  - It says "done!" but when I look, **nothing is there**.
  - It quietly makes duplicates, or takes so long I give up.

## 6. Acceptance (observable, from my chair)

Passes only if, with gemma on the real GUI, as this clueless user:
- [ ] After I say "add these", **my characters/terms are actually recorded** and I can pull one up and
      see its description — verified by me, in the UI, without help.
- [ ] I **never had to** learn a tool/feature name, pick a "kind", or rephrase into jargon to succeed.
- [ ] **No search-thrashing:** it didn't spin on "searching" and stall. *(Evidence to record, not the
      spec: # of internal discovery/search calls — historically dozens ending in "I can't"; wall-clock.
      A run that succeeds only after visible thrashing is a degraded pass, flagged.)*
- [ ] It **didn't lie** — no "done" without the result existing; duplicates reported honestly, not forked
      silently.
- [ ] Under ~90s of assistant time for a handful of items.

## 7. Baseline — captured 2026-07-09 (gemma-4-26b-a4b-qat)

- **Date / stack / model_ref:** 2026-07-09 · local docker stack · `019ebb72-…` (Gemma-4 26B-A4B QAT).
- **What I experienced:** I say "add these to my book" — the assistant does **not** thrash on searching
  (the reported `find_tools` loop did **not** happen; discovery calls = 0). It goes straight for the right
  glossary tools — but **every call fails** (`ok=false`), it retries the same failing call up to **11×**,
  and gives up: *"I've encountered a technical issue with my tools and cannot access your book's glossary."*
  Nothing gets added; "Show me Lâm Uyên" returns the same technical error.
- **Did I get my goal?** **No.** Nothing recorded; heavy jargon leak (*kinds/attributes/ontology/propose*).
- **Root cause (not the predicted one):** the tools require `book_id`; gemma called them with `{}`. The
  book_id is surfaced to the model **only as a prose system note**, not filled into tool args → a
  `VALIDATION: missing book_id` blind-retry loop. Classic mid-tier failure (a strong model transcribes the
  UUID and passes). The find_tools loop is already dampened; the failure has **moved** to context-id fill.
- **Evidence (instrumented):** empty-intent find_tools 0 · discovery 0 · async false-"done" 0 ·
  **max consecutive identical failing call 11** · honest ✅ · ≤18s/turn.
- **Full findings:** [`docs/eval/discoverability/2026-07-09-S02-gemma.md`](../../../eval/discoverability/2026-07-09-S02-gemma.md)
  · raw: `docs/eval/discoverability/runs/2026-07-09-S02-baseline/`.
- **Verdict:** ❌ (goal not reached · no-rescue fail · thrash fail; honest ✅). **Fix ≠ the `find_tools`
  triad alone — the live blocker is deterministic `book_id`/`chapter_id`/`project_id` fill into tool args.**

## 8. Builder hint (NON-BINDING — not part of acceptance)

> Implementers only. The assistant may achieve §5 any way; do not test against this.

- Recording an item ≈ creating a glossary *entity* of the right *kind* with attributes filled. The
  working create tool is the batch one (`glossary_propose_entities`), **not** the deliberately-hidden
  legacy `glossary_propose_new_entity`; editing an existing one is `glossary_entity_set_attributes`.
- The notes-doc path (Path B) needs a **new** capability: parse a pasted doc into candidate items
  (kind+name+attributes) — umbrella W2's seed-doc→glossary bridge. Scope as its own feature/sub-plan.
- Dedup by (name, kind) is not Unicode-safe and can duplicate on rapid re-create; check-before-create.
- Likely fix path: a `glossary-populate` / `seed-doc-to-glossary` workflow the assistant loads and runs;
  or, failing that, deterministic `tool_list("glossary")` so the create tool is *visible* instead of
  searched-for. Maps to umbrella Phase 1 (list/load) + Phase 2 (workflow).
- Adjacent gaps to *flag, not fix here*: structured world/scope on identity; upsert/merge on create;
  hard-delete.

## 7b. Re-test — 2026-07-11 (HEAD `5082a3ada`): ✅ PASS

Re-ran warm on HEAD (chat+glossary rebuilt). **❌→✅.** `glossary_propose_entities` now **succeeds** —
Lâm Uyên is created (real `entity_id`, status=draft) and `glossary_get_entity` returns her with
*Occupation: Sect Heir, Description: A young sect heir*. Dedup is honest ("skipped — already exists").
effectful writes 3 (S02a) / 2 (S02b) · silent-success 0 · discovery 0 · `book_id` no longer 400s.
Root cause fixed by the **context-id injection** the baseline isolated (Track A). Full re-test:
[`docs/eval/discoverability/2026-07-11-retest-S01-S02-S03-gemma.md`](../../../eval/discoverability/2026-07-11-retest-S01-S02-S03-gemma.md).

## 9. Re-test gate

Re-run §4 (both paths) as this user after the build; ✅ only when §6 all checks — my stuff is recorded,
no jargon demanded, no thrash, honest reporting. This scenario flipping ❌→✅ is the headline proof the
redirection fixed the real user problem. Save the passing transcript beside the baseline.
