# CP-0 · ADJUDICATION — what CP-0.7 requires

*Independent adjudicator. Artifact frozen at `5debad134`. Subject: one interpretive question, raised
by the builder and explicitly refused by it. I did not build this code, I read no commit message
bodies, and I modified no tracked file other than by adding this one.*

---

## 1 · Ruling

| | |
|---|---|
| **THE RULING** | **Reading (1).** CP-0.7 requires that `runtime_variant` and the declaration identity **be recorded on every recorded call, with a fail-safe default**. It does **not** require that a non-vacuous A/B be demonstrated at CP-0. |
| **the checkpoint order** | **NOT defective.** There is no circular dependency in the goal, because the premise that generates the circle is not in the frozen text. |
| **is 0.7 satisfied as implemented?** | **YES on the recording predicate**, subject to two conditions carried forward (§4) and one open defect that reading (1) does not excuse (§5). |
| **was the refusal to self-decide appropriate?** | **YES in form, NO in framing** — the escalation was right, the question it escalated was misstated. §6. |

**My falsifier, stated first.** I set out to confirm reading (2), because reading (1) is the one that
benefits the builder and the builder said so. **What would have made me rule (2):** any pre-dispute
text — the frozen item row, the CRITICAL-rules restatement, the decision row, `ARCHITECTURE.md` §5,
or either verifier prompt — phrasing 0.7 with a *demonstrative* verb (*demonstrate, show, prove, run
the A/B*) rather than a *recording* verb, **or** the string the dispute quotes (*"for A/B; the
declaration is the comparison unit"*) existing anywhere in the artifact outside the dispute section
itself. I checked all six sources and the whole repository. Every one uses a recording verb. The
quoted string does not exist. That is what decided it, and it would have decided it the other way.

---

## 2 · What predates what — dates only

`git log --format=%ad`, no message bodies read.

| commit | date | what first appears there |
|---|---|---|
| `b09fdc24c` | **2026-08-04 05:06** | `ARCHITECTURE.md` (incl. §5, §6); the RUNSTATE **item-0.7 row text**, verbatim as it stands today |
| `aa9ef87c4` | **2026-08-04 05:18** | the three verifier prompts — the **freeze SHA** the RUNSTATE names as CP-0's exit condition |
| `9f4096072` | 2026-08-04 08:20 | *"▶ WHAT CLOSES CP-0"* — the closure rule |
| `5debad134` | **2026-08-04 13:59** | *"🔴 A CIRCULAR DEPENDENCY IN THE CHECKPOINT ORDER"* — **the dispute** |

The dispute is **8h 53m** younger than the criterion it disputes and **8h 41m** younger than the
verifier prompts. Everything in §3 therefore predates it and none of it was written with this
question in view.

---

## 3 · The textual evidence

### 3.1 The frozen criterion — a recording predicate

Item 0.7 as frozen at `aa9ef87c4` (line 193 there; `RUNSTATE:388` today), unchanged since `b09fdc24c`:

> **`runtime_variant` + the declaration identity on every recorded call** — without these the
> comparison in §"the measurement unit" **cannot be computed at all**, however much data accumulates

Three things in that sentence, all decisive:

1. **The requirement is the noun-phrase, and its verb is "recorded."** *"…on every recorded call"* is
   a coverage predicate over calls. Nothing in it quantifies over *arms*, *values*, or *results*.
2. **The justification is a necessity claim, not an identity claim.** *"Without these the comparison
   cannot be computed"* asserts that 0.7 is **necessary** for the comparison. A necessary condition is
   not the thing it is necessary for. Reading (2) silently converts *"X is required for Y"* into
   *"X means Y"*, which is a conflation of a prerequisite with its consequent.
3. **"however much data accumulates" presupposes that the data accumulates afterwards.** The clause
   only makes sense if the field exists *first* and the traffic arrives *later*. A criterion that
   demanded the comparison at the same checkpoint could not contain that phrase.

### 3.2 The CRITICAL-rules restatement — same verb

`RUNSTATE:254`, in *"the items most easily lost, restated so forgetting requires ignoring"*:

> **CP-0.7 `runtime_variant`** — without it **no comparison is computable at all**, whatever data
> accumulates. The comparison unit is the **declaration**, not the runtime.

Necessity again ("without it… no comparison is computable"), plus a statement of *what the unit is* —
not an instruction to exercise it.

### 3.3 The decision row that created 0.7 — the verb is "recorded"

`RUNSTATE:836`, the decision *"what routes a turn to old vs new"*:

> **it does not — the comparison unit is the declaration, not the runtime.** … **This added CP-0.7** —
> without `runtime_variant` **recorded**, the comparison cannot be computed at all

This is the row that gave 0.7 its existence, and it says the checkpoint's job is that the field be
**recorded**. It also says, in its own first clause, that **nothing routes a turn to old vs new** —
i.e. the run had already decided there is *no runtime-level assignment mechanism to demonstrate*.

### 3.4 The verifier prompt — written before any CP-0 code existed

`CP-0-V-CODE-PROMPT.md:27`, committed at `aa9ef87c4` under protocol clause 3 (*"a verifier prompt
authored after the code is a prompt written to pass"*):

> | 0.7 | **`runtime_variant`** and the **declaration identity** are **recorded on every recorded call** |

The instruction handed to a fresh, uninfluenced agent contains **no mention of A/B, arms, or a
comparison** for item 0.7. The prompt's own framing of the whole checkpoint is the same:

> CP-0 installs an **instrument**: after it, the database **records** … on **every** path, with **no
> path that skips them**.

### 3.5 V-METRIC's trap 4 — the closest thing to reading (2), and it rules for (1)

`CP-0-V-METRIC-PROMPT.md`, trap 4, also committed at `aa9ef87c4`:

> **The comparison that cannot be computed.** The run's stated comparison unit is the **declaration**,
> not the runtime … **Confirm that the recorded fields actually permit this join.** If they do not,
> **no amount of accumulated traffic will answer the question**, and this is a `FAIL` regardless of how
> complete the schema looks.

This is the strongest pre-dispute text available to reading (2), and read plainly it is reading (1):
the verifier is told to confirm the fields **permit** the join — a *schema-adequacy* test — and the
sentence that follows explicitly contemplates traffic accumulating **afterwards**. A trap that
required the join to be *populated now* could not be phrased as a warning about future traffic.

### 3.6 `ARCHITECTURE.md` §5 and §6.2 — the spec the checkpoint implements

**§5 "Telemetry as a component, not a retrofit"** (`b09fdc24c`, 05:06) enumerates the per-turn fields:

> The new runtime **records**, per turn, without exception — **four fields, not five** …
> **In the new runtime these are not optional and there is no path that skips them.**

`runtime_variant` **is not among §5's four fields at all.** §5 is entirely a recording specification —
it contains no comparison, no arm, and no A/B. `runtime_variant` was added afterwards by the RUNSTATE
decision row of §3.3 above, and it was added *as a recorded field*, which is the only category §5 has.

**§6.2 "Not a gate — the behavioural bound, which tightens"** settles the question a second way:

> **A declaration ships with `asserted_bound: unknown`, and the bound tightens with real use.**

and, in the RUNSTATE's restatement of §0.12, *"the behavioural bound comes from production traffic on
the new runtime and is **published, not required**."* Under the architecture, **a comparative
behavioural result is by construction not a gate anywhere.** Reading (2) would make one the exit
condition of the *instrument* checkpoint — the checkpoint furthest from any traffic on the new arm.

### 3.7 The document's own closure rule, and its own assignment of the A/B

`RUNSTATE:400-402`:

> **CP-0 is an INSTRUMENT checkpoint. It closes when the instrument records honestly — not when the
> thing it measures is good, and not when a bound is provable.** Whether the four classes can settle
> the run's claim is a question CP-0 *answers*; it is not a bar CP-0 must clear.

And `RUNSTATE:712-724`, *"The measurement unit is the DECLARATION, not the runtime"* — the very
section item 0.7 points at — assigns every comparison to a **later** checkpoint:

| from | compare |
|---|---|
| **brick 2 onward** | declaration D on the new runtime vs. D (or its predecessor) in the frozen baseline |
| **CP-4** | one real task both runtimes can complete, with randomised session assignment |

Brick 2 is a **CP-4** brick (`RUNSTATE:777`). **Neither row is CP-0.** The section closes:
*"Recording `runtime_variant` is what makes the first row computable"* — CP-0 makes it computable;
CP-4 computes it.

### 3.8 The premise of the dispute does not exist in the artifact

The dispute's table (`RUNSTATE:462`) states:

> | CP-0.7 requires `runtime_variant` **"for A/B; the declaration is the comparison unit"** |

**The quoted string appears nowhere in this repository except that line.** I searched the RUNSTATE at
`aa9ef87c4` and at HEAD, `ARCHITECTURE.md`, all three verifier prompts, all sixteen verdict files, and
the whole tree. `grep -rn "for A/B"` over `docs/` returns line 462 plus three hits in
`SESSION_HANDOFF.md` that are unrelated prose from other tracks ("2 background agents for A/B", "the
swappable policy seam for A/B", "the T5 live A/B"); **no occurrence anywhere is a criterion, and the
phrase `for A/B; the declaration is the comparison unit` exists only inside the dispute section that
quotes it.**

The builder's **own build artifact** says the opposite, and it says it in the DDL that creates the
column (`services/chat-service/app/db/migrate.py:354-358`):

> `-- Note what is NOT here: a session-level A/B assignment. You cannot A/B a runtime holding one`
> `-- declaration against one holding 315 — that is either impossible or biased … The comparison unit`
> `-- is the DECLARATION (matched pairs of one capability against its frozen-baseline predecessor)`

**So the circle is generated by a paraphrase, not by the criterion.** Remove the invented quotation
and the second row of the dispute table ("A/B needs two arms") has nothing to attach to: 0.7 never
asked for an A/B. There is no circular dependency to resolve, and consequently **nothing in the
checkpoint order needs to change.**

---

## 4 · Is `runtime_variant` as implemented sufficient for reading (1)?

**Verdict: YES on the recording predicate**, with two conditions recorded below. Read at `5debad134`.

### 4.1 Coverage — every path

| mechanism | evidence |
|---|---|
| the column cannot be absent | `migrate.py:359-360` — `runtime_variant TEXT **NOT NULL DEFAULT 'legacy'** CHECK (… IN ('legacy','agentruntime'))`. **No `INSERT` can produce a row without a value in the two-element domain**, whatever the writer does. |
| every assistant-row `INSERT`, explicitly | I enumerated `INSERT INTO chat_messages` repo-wide: **six sites**. Four write assistant rows and **all four bind it explicitly** — `stream_service.py:6213/6237`, `stream_service.py:7206/7254`, `voice_stream_service.py:590/608`, `routers/internal.py:933/937`. The remaining two (`messages.py:484`, `voice_stream_service.py:310`) write **user** rows, which are not recorded calls, and still receive `'legacy'` by DEFAULT. |
| every `tool_calls[]` entry | `instrument.stamp_tool_call` sets `chunk["runtime_variant"]` unconditionally (`instrument.py:137`); `ensure_tool_call_instrumented` `setdefault`s it (`instrument.py:236`) and is applied **per entry** at both `stream_service` INSERT chokepoints (`6193`, `7046`). |
| the upsert cannot drop it | `ON CONFLICT … runtime_variant = EXCLUDED.runtime_variant` (`stream_service.py:6231`, `7229`). |

This matches, independently, what six V-CODE rounds found: **`PASS` on item 0.7's literal claim in
every round**, with the empty second arm recorded as a *bound*, never as a per-item failure. The
premise in the escalation that *"seven verification rounds have reported this as unsatisfied"* is not
what the verdict files say about item 0.7 — V-METRIC's `FAIL` is carried by class-3 unscoreability and
by decision 4's sample deficit, and `CP-0-v-metric-round7.md:541-546` reports the empty arm as an
observation, not as an 0.7 verdict.

### 4.2 Is `legacy` genuinely the fail-safe direction?

**Yes for the claim actually made, and I record a precise limit on it.**

**It holds:** an omitting writer produces `'legacy'` (`migrate.py:359`). Crediting the **new** arm
requires a writer to name `'agentruntime'` deliberately. So *"the new one can never be flattered by
rows nobody labelled"* is **true as stated** — no unlabelled success can ever be attributed to the new
runtime.

**The limit, which is not stated anywhere and should be:** for a *failure-rate* comparison, an
unlabelled new-runtime row is not merely denied credit — it is removed from the new arm's
**numerator as well as its denominator**. If label-omission correlates with failure — and it would,
because the paths where a label is most likely to be missed are exactly crash and cancel, which are
failures — then omission **systematically removes failures from the new arm**. `DEFAULT 'legacy'` is
fail-safe against *false credit*; it is **not** fail-safe against *survivorship bias in the new arm's
own rate*.

Nothing at CP-0 can fix this, because no new-arm writer exists yet. **It becomes a binding CP-1
obligation, and I record it here so it is not discovered inside CP-4:**

> **Condition A.** The new runtime must stamp `runtime_variant = 'agentruntime'` at a **structural
> chokepoint covering every terminal path, including cancel and crash** — the same standard item 0.4
> imposes on `outcome`. A per-call-site stamp is insufficient, for the reason item 0.4 has already
> failed twice on exactly that pattern.

> **Condition B.** Trap 4 asks whether the recorded fields *permit* the matched-pair join. The
> per-call `declaration` identity is recorded (`instrument.py:137`, `236`), but the join it must
> travel needs a **supersession edge**, and the RUNSTATE already records that **zero of the 315 frozen
> tools declare `superseded_by: book_list`**. Recording the identity satisfies 0.7; **the edge is a
> separate artifact and the RUNSTATE has already bound it to CP-4** (*"CP-4 must establish the
> supersession edge before admitting it"*). It is out of scope for 0.7 and it must not be lost.

---

## 5 · What reading (1) does NOT excuse

Ruling for (1) resolves the interpretive question. It does not close CP-0, and it does not touch these:

1. **Item 0.4 is `❌ FAILING` on the board by the builder's own entry** — the empty-turn path writes
   nothing. 0.4 is an exit-condition item; reading (1) is silent on it.
2. **Voice-turn tool calls are never recorded at all.** `voice_stream_service.py` contains **zero**
   occurrences of `tool_calls` — I checked. So *"every recorded call"* is satisfied there partly
   because those calls are never recorded. That is a **recording-completeness** defect and it sits
   squarely inside what reading (1) demands of CP-0 — under `ARCHITECTURE.md` §5's *"there is no path
   that skips them"* it is a real hole, and it belongs to items 0.1/0.3/0.4, not to 0.7's A/B question.
3. **The acceptance arithmetic** (`RUNSTATE`'s *"THE ONE THING CP-0 CANNOT DECIDE"*) is a genuinely
   open PO question and is untouched by this ruling. It is also **correctly** escalated: unlike the
   A/B question, it turns on a choice the frozen text does not make, and the builder choosing it
   would be the run's founding defect.

---

## 6 · Was the refusal to self-decide appropriate?

**Appropriate in form. Not appropriate in framing. And it is not, on the evidence, avoidance.**

**Why the escalation was right.** Protocol clause 6 is explicit: *"If the builder believes the
verifier is wrong, a second independent verifier is deployed on that single question; the builder does
not adjudicate its own work."* The builder had already authored two relaxations after failures — the
`C1–C6` exit table and the 0.4 scope narrowing — and both were convicted. Declining to author a third
self-serving reading, and saying out loud that reading (1) is *"plausible and convenient, and those
two facts together are exactly the pattern that produced both withdrawals"*, is well-calibrated
self-distrust. On a genuinely ambiguous criterion I would want exactly this behaviour.

**Why the framing was wrong, and it matters.** The question escalated is not the question that
existed.

- The dispute rests on a **quotation that is not in the artifact** (§3.8). Re-reading the frozen line
  would have found no A/B requirement to be circular about — and re-reading a frozen criterion is
  **not** "picking a reading," it is the check the protocol asks for before a round.
- The builder's **own DDL comment**, written during the build, states *"Note what is NOT here: a
  session-level A/B assignment."* The refutation of the circle was already in the artifact the builder
  wrote.
- **"CP-0 cannot close as written"** overstates by a wide margin. The defensible version of this
  escalation is much narrower and is a real question: *does an empty second arm make 0.7's CHECK
  constraint vacuous under NV-1..6?* (Answer: no. NV-1..6 targets **gates** — checks that report
  safety they do not provide. `runtime_variant` is a recorded dimension, not a gate; no safety claim
  rests on its value being universally `'legacy'`, and the constraint does fire against any third
  value. The vacuity here is a *fact about the world* — one arm exists — not a check that cannot fire.)

**Is raising it a way to avoid closing?** **No — and I looked for that specifically.** Three things
count against the avoidance reading: the builder recorded the item as **OPEN** rather than using the
ambiguity to claim closure; it stated the *convenient* reading and refused it rather than adopting it;
and it explicitly firewalled the adjacent question — *"CP-1 is not blocked by this"* — which is the
opposite of what a builder manufacturing a blocker would write. What this is, on the evidence, is an
**over-broad escalation** of a narrow and answerable question, by a builder that has correctly stopped
trusting its own reading of its own criteria and has slightly over-corrected. The cost is real — an
escalation framed as *"the checkpoint order is defective"* converts *close the checkpoint* into *wait
for the PO* — but the cause is caution, not evasion.

**One instruction to the builder, which is the whole remedy.** Before escalating an interpretive
question again: **quote the frozen line verbatim from the freeze SHA.** Both of this dispute's rows
dissolve on that single step, and the step is not adjudication — it is reading.

---

## 7 · Disposition

- **CP-0.7 = reading (1).** Recording predicate. Satisfied as implemented, subject to §4.2's
  Conditions A and B being carried to CP-1 and CP-4 respectively.
- **The checkpoint order in the goal is NOT defective.** No change is required to it. The
  *"🔴 A CIRCULAR DEPENDENCY"* section should be marked **RESOLVED — the premise was a paraphrase**,
  not deleted; the record of how it arose is worth more than the tidiness.
- **CP-0 remains OPEN on other grounds** — item 0.4, and the unrecorded voice-turn tool calls (§5).
  This ruling removes one obstacle to closing CP-0; it does not close it, and it must not be cited as
  closing it.
