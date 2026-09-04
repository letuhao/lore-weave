# GUI-parity triage — the remaining 95, domain by domain

Continues [`2026-09-04-first-release-readiness-and-gui-parity.md`](2026-09-04-first-release-readiness-and-gui-parity.md),
whose gate and census shipped. **That plan's goal is only half met and this is the other half.**

---

## 0. Why this plan exists, stated exactly

The previous plan's board is fully ticked and its own goal is **not** achieved. The gate can go red
and the first-release gaps are measured — but *"every agent-attemptable write has a manual GUI path"*
was verified for **23 of 118** rows. The other **95 are `UNTRIAGED`**.

🔴 **`NONE = 0` does not mean "no gaps".** It means no gaps among the 23 that were looked at.
Reading that zero as parity would be exactly the false metric the gate was built to prevent — with
the gate's own number. **`UNTRIAGED` is the absence of a verdict and never counts as parity.**

For scale: `world_delete` was **1 of those 23**, and it turned out to be a 100%-failure capability
with no manual path at all.

---

## 1. The ranking, measured not guessed

Agent calls and failures per untriaged domain, from the live chat store:

| domain | untriaged | agent calls | **failed** | rate |
|---|---:|---:|---:|---:|
| **composition** | 39 | 1740 | **1189** | 68% |
| **knowledge** | 14 | 1410 | **930** | 66% |
| **glossary** | 18 | 956 | **591** | 62% |
| translation | 8 | 326 | 101 | 31% |
| jobs | 2 | 88 | **88** | **100%** |
| settings | 7 | 69 | 64 | 93% |
| registry | 5 | 45 | **45** | **100%** |
| book | 1 | 10 | **10** | **100%** |
| lore_enrichment | 1 | 10 | **10** | **100%** |

**Rows are ordered by absolute failures**, because that is where users are actually being hurt.
⚠️ But four domains fail **100%** — `jobs`, `registry`, `book`'s last row, `lore_enrichment`. That
is `world_delete`'s exact signature (92/92, no manual path), and it is why those small rows are not
at the bottom by accident: they are cheap and they are the likeliest total gaps.

---

## 2. How a domain is triaged, so the verdicts mean something

For each tool: `UI` (route + a **mounted** `data-testid`) · `UI_NO_TESTID` · `AGENT_ONLY` (with its
reason) · never left `UNTRIAGED`.

🔴 **The three things that already went wrong once, and will again:**

1. **Name-matching does not work.** Three auto-matchers were each refuted by a known-positive
   control. The FE's vocabulary differs from the tool vocabulary. Triage by *reading the feature
   folder*, not by matching identifiers.
2. **A testid is not enough — the component must be MOUNTED.** And the gate's mounted check is a
   heuristic with **35 known false positives**: registry mounts, context providers, Tiptap node
   views. **A red there is a prompt to look, not a proof.**
3. **I declared a testid from memory that did not exist** (`editor-root`). Every declaration is
   verified by running the gate before commit, never by recall.

---

## 3. Board

- [ ] **T1** — **composition (39 tools, 1,189 failures)** — the biggest by a distance. Triage all 39, close what
  it finds, tighten `MAX_UNTRIAGED` in the same commit.
- [ ] **T2** — **knowledge (14, 930).**
- [ ] **T3** — **glossary (18, 591).**
- [ ] **T4** — **the 100%-failure cluster (9 rows)**: `jobs` 2, `registry` 5, `book`'s
  `book_structure_edit`, `lore_enrichment` 1. Small, and every one fails every time — the
  `world_delete` signature. Cheap to triage and the likeliest total gaps.
- [ ] **T5** — **translation (8, 101)** and **settings (7, 64)**, whichever remain.
- [ ] **T6** — **tighten the ratchets to the final measured numbers**, and record what `AGENT_ONLY`
  legitimately covers, so the next reader can tell a declared exemption from a forgotten row.
- [ ] **R6** — an **orphaned turn** (no assistant row; `outcome='failed'` on the USER message) shows
  the author nothing. D2's badge renders on an assistant message and there is none, so it cannot
  reach this. Reproduction in the previous plan's §R4.
- [ ] **R7** — a model under **~11K context cannot chat at all** (the tool surface alone is ~9.7K)
  and nothing warns at registration. The user finds out by watching a message vanish — via R6.
- [ ] **D3** — **STOP CONDITION.** `platform_models` is empty, so the model story is **BYOK**, and
  the UI says so at both the point of failure and the point of repair. Is BYOK-only the *intended*
  first-release posture? Owner's call, carried over unanswered.
- [ ] **D4** — **STOP CONDITION.** One cloud-model run. Everything so far was proven on one local
  model. Costs money; needs an explicit yes and a stated call count. Carried over unanswered.

---

## 4. The loop, and what makes it a ratchet

Each `T` row ends by lowering `MAX_UNTRIAGED` in `scripts/gui-parity-gate.py` **to the number that
row actually reached**, in the same commit, with the reason written in. A domain that has been
triaged cannot silently come back, and a tool added tomorrow lands as `UNTRIAGED` above the ratchet
and reddens CI until someone gives it a verdict.

`MAX_NONE` stays at **1** until T6. Lowering it to 0 while 95 rows are unlooked-at would turn the
next honestly-discovered gap into a build break before anyone could triage it — a ratchet that
punishes finding things teaches people not to look.

**RESUME: T1 — triage composition's 39 write tools, the domain with 1,189 measured agent failures**

---

```goal-prompt
goal: every one of the 118 live write tools carries a real verdict, the UNTRIAGED count reaches zero, and every gap it uncovers is closed or declared
po_decisions: [D3, D4]
rules: |
  1 $0. Local models only. A PAID run needs an explicit yes and its CALL COUNT stated first. platform_models is EMPTY - keep it that way.
  2 Content-creating runs use a NEW throwaway book, never the dogfood book, never an existing one.
  3 Verify the DEPLOYED IMAGE before believing a live result, by a whole-file property and not the symbol you just added.
  4 UNTRIAGED is the ABSENCE of a verdict and never counts as parity. Never report NONE=0 as "no gaps" while rows are untriaged.
  5 Do NOT triage by name-matching. Three matchers were each refuted by a known-positive control; read the feature folder.
  6 A UI verdict needs a route AND a data-testid that EXISTS and whose component is MOUNTED. Run the gate before commit - a declaration from memory is how editor-root got shipped.
  7 The gate's mounted check has 35 known false positives (registry mounts, providers, Tiptap node views). A red there is a prompt to LOOK, not a proof of a gap.
  8 AGENT_ONLY is legitimate and must carry its reason. A silent NONE dressed as agent-only is the failure this metric exists to catch.
  9 A ratchet moves in the SAME COMMIT as the work that moved it, with the reason written in. MAX_NONE stays 1 until T6.
  10 Attribute a red thing before fixing it. 5 FE and 18 scripts/ failures are known to pre-date this work.
discipline: |
  Numerator and denominator must measure the same population - stratify before pooling.
  Verify the pointer before declaring evidence missing, and grep for the route before blaming a service.
  A pending Tier-A card reads as a hung turn on a database poll: watch outcome='awaiting_input' too.
  sed -i rewrites every line ending on this repo's CRLF files - edit with Python or Edit, and check cmp AND git diff --stat after a bite.
  A pipe to head/tail reports the PIPE's exit, not the command's. Capture to a file when the exit code matters.
stop: |
  a write would touch a non-throwaway book or database
  a run would call a model that is not local
  a product decision is owed: D3, D4
  a sealed decision turns out to be wrong
```
