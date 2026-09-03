# RT-0.13 — adversarial review of `ARCHITECTURE.md` §0.13 against its stated PURPOSE

**HEAD at review:** `4ec3f2a83318d0343c14c31bdd5645619fd9e16d` — verified with `git rev-parse HEAD`,
working tree clean for `docs/specs/2026-08-03-agent-runtime-unification/` and `docs/plans/`.
**Artifact:** `ARCHITECTURE.md` §0.13 (lines 70–209), read against §0.1 (49–66), §0.12 (781–828),
§6 (1085–1186), `RETROSPECTIVE-CP0.md`, `docs/plans/2026-08-04-agent-runtime-RUNSTATE.md`, and the
provider path in code.
**Method:** premise granted throughout — *a non-deterministic substrate makes model noise and
substrate noise indistinguishable*. Only the **conclusion** is attacked. Author's commit messages not
read; the one prior revision consulted was `HEAD~1`'s **file content**, to establish what the edit did
to its neighbours.

---

## Verdict summary

| # | claim under attack | verdict |
|---|---|---|
| **0** | *(not asked; found while reading)* §0.13 is a clean insertion | 🔴 **FALSE — it silently deleted §0.3.** Thirteen live cross-references now dangle, including §9's reading order |
| **1** | a deterministic substrate makes model behaviour attributable | 🔴 **does not follow.** Determinism buys *power* and *debuggability*, not attribution. Three named confounds survive it intact |
| **2** | CP-0's unsettleable rate claim was partly a determinism problem | 🔴 **unsupported, and the evidence points the other way.** The retrospective's actual attribution is instrument non-equivalence, which determinism does not touch; the cited number is a superseded one; the cited defect is a *disclosure* defect the run already closed |
| **3** | replay of a deterministic layer is legitimate evidence, §0.12 conflated two layers | 🟢 **the distinction is real and §0.12 survives it** — but §0.13 never draws the line it needs, and §0.13.4 supplies the premise for exactly the readmission §0.12 blocks |
| **4** | recording `seed` makes the model call replayable | 🔴 **worth approximately nothing here, and one field is worse than nothing.** Proven by execution: the transport type silently drops both `seed` and `top_p` |
| **5** | scope creep vs. architecture | ⚖️ **scope creep is the stronger reading** — on the clause's own "cheapest moment" logic, which the evidence contradicts |

**Overall: §0.13's *properties* (P7, P8) are sound and the gap it names is real. Its *purpose
argument* is not carried.** The clause is a good engineering property wearing an epistemological
justification that does not hold, and it paid for that costume by destroying a section.

---

## Finding 0 — the clause practises the defect it forbids *(found, not asked)*

§0.13 opens by justifying its own placement:

> `ARCHITECTURE.md:72-73` — *"Numbered by order of adoption, placed here by order of reading: it is
> §0.1's twin and the two are unreadable apart."*

At `HEAD~1`, line 70 held `### 0.3 The Ceiling Test — every mechanism must pass it *(PO, 2026-08-04)*`,
running to line 116. At HEAD, §0.13 occupies line 70 and **§0.3's heading is gone**. A byte-diff of
`HEAD~1:70-116` against `HEAD:165-209` returns exactly two removed lines — the heading and its blank
line. The body is identical.

**Consequence: the entire Ceiling Test now sits inside `#### 0.13.4 What this changes about CP-0 — and
it does not reopen it`.** §0.13.4's own subject ends at line 164. Lines 165–209 — the Opus 4 → 4.5
numbers, the enabler/ceiling verdict table, the membrane-as-ceiling risk — are about a different
question, and a reader now attributes them to a CP-0 re-attribution they have nothing to do with.

Thirteen references point at the deleted heading:

- `ARCHITECTURE.md:212` *"Every ceiling in §0.3 has the same origin"*
- `ARCHITECTURE.md:418, 425, 518, 519, 537, 542, 689, 817, 1155`
- `ARCHITECTURE.md:1231` — **§9's reading order**: *"Read §0, §0.1, §0.2, then §0.3 onward."*
- `ARCHITECTURE.md:1235` *"§1–§8 were the first draft and §0.3–§0.12 are the correction layer"*
- `SPEC.md:1141` *"Read `ARCHITECTURE.md` §0.3–§0.11 first"*
- `RUNSTATE:434` *"except P6 (§0.3)"*

This is §0.1's own defect, committed by §0.1's twin:

> `ARCHITECTURE.md:64-66` — *"it was wrong because it narrowed silently, and then the surface told the
> model the list was complete… an exclusion that does not register is a runtime contract violation."*

A section was removed; the removal registered nowhere; the document's index still tells the reader the
list is complete. It is also a **replay failure in the sense §0.13.2-D defines**: the record (this
file) no longer permits reconstruction of which clause a §0.3 citation resolves to. The clause is not
merely inconsistent with its thesis — it is a live counter-example to it, in the same commit.

---

## 1 · Does determinism buy attributability?

**The claim.** The purpose, as framed: *if the substrate is non-deterministic, model noise and
substrate noise cannot be told apart, so nothing about the model can be measured.* The document's own
form:

> `ARCHITECTURE.md:84-86` — *"Disclosure without determinism yields an **honest record of a chaotic
> process**. You can read exactly what happened and still not make it happen again — which is precisely
> what CP-0 delivered: a good instrument, and a claim that could not be settled."*

**It does not follow, and the error is a category one: attribution is a property of the DESIGN, not of
the substrate.** What makes an arm's effect attributable is *exchangeability* — that arm assignment is
independent of everything else that could move the outcome. Substrate noise that is independent of
assignment is **variance**, not **bias**. Variance is answered by `n`. So under a randomised design a
noisy substrate costs sample size and nothing else; you never need to tell the two noises apart,
because the assignment guarantees they are uncorrelated.

**Three confounds that survive a perfectly deterministic substrate.**

1. **Unrecorded-input confound.** A substrate can be a perfect, total function of `(query, DB state,
   user prefs, book contents)` and be irreproducible because three of those four were never recorded.
   §0.13 knows this — layer A (`:116`) demands input closure — but layer A is *not verifiable from the
   inside*. You can never prove you have named every input; you can only fail to find one more. That
   makes input closure **a bound that tightens, not a gate that opens** — §0.12's own shape (`:810`),
   applied to §0.13. The clause does not admit this about itself, and it asserts the strong form:
   *"the same inputs produce the same surface"* (`:75-76`) reads as a guarantee when it is a
   conditional whose antecedent is unfalsifiable.

2. **Covariate/temporal confound.** CP-0's arms are not randomised — they are a **frozen historical
   corpus** versus a **new runtime**, i.e. a before/after split. Everything that changed with time
   (model version, prompts, the one dogfooding user's habits, test debris in the shared dev DB —
   `ARCHITECTURE.md:806-808`) is confounded with arm. Determinism of the substrate randomises nothing
   and matches nothing. Two deterministic runtimes compared across time are still a confounded
   comparison.

3. **Downstream-of-the-stochastic-node confound.** §0.13 concedes its scope at `:76` — *"Above the
   model call, nothing is promised."* Every quantity CP-0 actually measured — carry-forward rate,
   prose-as-error rate, arm E's 0/3 — is **above** the model call. Determinism below a stochastic node
   gives you a reproducible *prompt*, not a reproducible *outcome*. You can re-run the same lottery
   with the same ticket printer. That is real value for **debugging one incident**; it is not
   attribution of a rate.

**What would additionally have to hold** for the clause's conclusion to be true: randomised or matched
assignment; an instrument identical in both arms; a verified (not merely asserted) input closure; a
pre-registered metric; and enough `n` for the residual stochasticity that quarantine does not remove.
Determinism contributes to the third and helps the fifth by shrinking variance. It is neither
necessary nor sufficient for attribution.

**The sharpest form of the objection.** The clause's stated benefit is *attribution*; its real benefit
is *statistical power* — a smaller `n` for the same effect. CP-0's blocker was `n`. So the honest
version of §0.13.4 — *"determinism would have reduced the required sample"* — is defensible and is
**not** the argument the clause makes. It makes the stronger, false one, and thereby argues past its
own best case.

*One version of the claim IS defensible and the clause does not make it:* if substrate drift is
**correlated with arm assignment** (deployment order, warm caches, a hash seed differing between the
two processes), that is genuine bias and no `n` fixes it. A temporally-split A/B is exactly the design
where that risk is highest. That argument is available, is about *arm-correlated* drift, and appears
nowhere in §0.13.

---

## 2 · The CP-0 re-attribution (§0.13.4)

**What the clause says** (`ARCHITECTURE.md:151-157`):

> *"CP-0's retrospective concluded the rate claim could not be settled on this corpus, and attributed
> it to **sample size** (548 frozen failures against 743 needed). Under this clause that attribution is
> **incomplete**:*
> *> **The frozen baseline was supposed to be the deterministic control arm. It was not.**
> *> `budget_names_by_tokens` was query-dependent — **87 candidate tools for one message and 101 for
> *> another** — so the control varied per input. **No sample size fixes a control that moves.**"*

**Verdict: not supported. It is a story that fits, and four separate checks reject it.**

### 2a · The retrospective does not attribute it to sample size

`RETROSPECTIVE-CP0.md` never mentions 548, 743, or a power calculation. Its stated cause is
**instrument non-equivalence**, quoted from V-METRIC:

> `RETROSPECTIVE-CP0.md:51-53` — *"The baseline can only be derived from error-prose signatures
> (pre-CP-0 rows have no `source`), while the new runtime classifies structurally and completely.
> **Those are different instruments**, so not-a-real-dispatch cannot be compared between arms — **no
> `n` fixes that.**"*

That is a **measurement-validity** failure, and determinism does not touch it. A perfectly
deterministic legacy runtime would still be frozen, still lack `source`, still be a different
instrument. §0.13.4 therefore corrects an attribution the retrospective did not make, while leaving
the one it did make untouched. Note also that *"no `n` fixes that"* — the retrospective's phrase — has
been re-used at `:157` as *"No sample size fixes a control that moves"*, transplanted onto a different
subject.

### 2b · The number is a superseded one

`:152` cites *"548 frozen failures against 743 needed"*. The record:

- `CP-0-v-metric-round5.md:764` — *"The baseline holds **548** unscripted real errors in total. The
  requirement is **748 per arm**."*
- `CP-0-v-metric-round6.md:34` — *"🔴 **REVISED, and slightly worse.** The frozen side holds **522**
  unscripted real errors, **not 548**, against **743** needed per arm. Deficit **221**."*
- `RUNSTATE:31` (the current, binding text) — *"**522 unscripted real errors against 743 needed per
  arm**"*.

§0.13.4 pairs round 5's **withdrawn numerator** with round 6's **corrected denominator** — a figure
that appears in no round. In a clause whose entire subject is *"the record carries enough input to
reconstruct the output"* (`:75-76`), the citation is not reconstructable from any record. Small in
magnitude, disqualifying in kind.

### 2c · The cited defect is a DISCLOSURE defect, already owned and already closed

The 87-vs-101 finding is filed by the run itself under **P1**, a disclosure property:

> `RUNSTATE:89` — *"🔴 **a narrowing stage nobody instrumented.** The pass-1 candidate pool is
> **query-dependent** — 87 tools for one message, 101 for another… Something picks ~100 of 315
> **before** `hot_seed` and **registers nothing**."*

*Registers nothing* is P1, verbatim. And it was largely closed as P1:

> `RUNSTATE:50` — *"🟡 **237 → 4.** `domain_not_selected` closed the query-dependent hole… Residual:
> **4 named tools, deterministic**."*

So the flagship evidence for *"a genus the claim set was missing"* is a case the existing genus
diagnosed, owned, and fixed. §0.13.4 re-labels a closed disclosure defect as an open determinism
defect. That is double-counting, and it is the load-bearing exhibit for the new genus.

### 2d · The central inference is a conflation — of *deterministic* with *input-invariant*

This is the decisive point. §0.13's own definition (`:75-76`) is *"the same inputs produce the same
surface."* A surface that yields **87 candidates for message A and 101 for message B is a textbook
function of its input.** It violates determinism only if the *same* message yields 87 on one call and
101 on another — which nothing in the record establishes, and which `RUNSTATE:50`'s *"4 named tools,
**deterministic**"* argues against.

`RUNSTATE:56` commits the same slip inside P7's own row: *"Legacy's own surface is query-dependent
(**87 vs 101 candidates** for two messages)"* — offered as a P7 violation, where P7 reads *"the surface
is a FUNCTION of its recorded inputs."* Query-dependence is what a function **is**. The genuine defect
in that same row is a different one, and it is stated correctly right beside it: *"the record holds
outputs and not inputs."* That is **layer A, input closure** — not determinism.

**And the slogan is backwards for the movement it evidences.** Per-input variation is *within-arm
variance*, and sample size is precisely the remedy for it, provided both arms draw from the same input
distribution. *"No sample size fixes a control that moves"* is true only for **arm-correlated** drift,
which 87-vs-101 is not evidence of.

**What a deterministic control arm would actually have changed about CP-0's conclusion: nothing
material.** It would not have supplied `source` to frozen rows (2a). It would not have added 221
failures to a frozen side that cannot grow. It would not have made classes 3 and 4 scoreable —
`RUNSTATE:31` records two of four classes *"ruled **unscoreable across arms at any n**"*, a
measurement-definition problem. Its one real contribution — lower variance, hence a smaller required
`n` — is the argument §0.13.4 declines to make.

**Aggravating context:** the rate claim was **already withdrawn** a day earlier —
`RUNSTATE:27-31`, *"✅ THE CLAIM IS NOW A PROPERTY CLAIM — PO decision, 2026-08-04 (option C). The
rate-based claim is withdrawn."* §0.13.4 concedes at `:159` that *"CP-0 stays closed and the legacy
instrument stays frozen as-is."* So the re-attribution changes no decision, corrects no live claim, and
exists solely to motivate the new genus — which makes its four defects load-bearing rather than
incidental.

---

## 3 · Replay versus §0.12

**§0.12's rule** (`ARCHITECTURE.md:798-799`):

> *"**A failure in test is information — it reproduces a real defect. A success in test bounds nothing.**
> Test evidence may **reject** a declaration. It may never **admit** one."*

**What it rejected** (`RUNSTATE:659`): option B, *"replay the frozen baseline corpus through both
runtimes offline"* — *"it is synthetic, and §0.12 says a test may reject but never admit."*

**What §0.13 proposes** (`:127-132`, layer D):

| | asks | needs | used for |
|---|---|---|---|
| **fidelity** | did the record match what the code **at that time** would produce? | `code_revision` + that code | audit, incident |
| **drift** | does **today's** code produce the same surface for that input? | the record alone | **a CI gate, every commit** |

**Which is right: both, and they are not in conflict — but the clause never says why.**

The drift gate is a **rejector**. Its output is *"today's code disagrees with the record"*, which fails
a commit. §0.12 permits that in terms: *"Test evidence may **reject**."* Option B was a different
animal — a replay of the corpus to *measure carry-forward rate*, an **outcome above the model call**,
offered to **admit** a claim by manufacturing `n`. §0.13.4's own boundary settles it: `:76` *"Above the
model call, nothing is promised"*, and layer C (`:124-125`) *"the record marks where determinism ends."*

**So what stops the same argument readmitting the synthetic runs?** The layer line — replay may
produce evidence only about the **surface** (below the seam), never about the **outcome** (above it).
That line exists in §0.13 and is never connected to §0.12. The clause asserts the reclassification and
omits the limiting principle, which is the only thing standing between it and option B.

**And §0.13.4 actively erodes the line it needs.** *"No sample size fixes a control that moves"*
(`:157`) says the blocker was a moving control rather than `n`. Fix the control, and the natural
reading is that the corpus becomes settleable — which is option B's argument with the determinism
premise supplied. §0.13.4 does not draw that conclusion. It leaves it one step away, unguarded, in a
document that has already had to withdraw one acceptance criterion for exactly this reason.

**Judgement: §0.12 stands unamended. §0.13's replay is admissible under §0.12 as a rejector without any
"conflation" needing to be conceded — and the clause's framing of §0.12 as having conflated two layers
is, on the text, unnecessary to its own case and corrosive to the boundary that protects it.**

---

## 4 · Is the seed worth anything?

**§0.13.3** (`ARCHITECTURE.md:141-147`):

> *"Sampling is probabilistic **and seedable**, and this repository passes **no seed at all** — checked,
> not assumed: `seed` appears nowhere on the provider path. Recording
> `{model_ref, seed, temperature, top_p, prompt_hash, block_hashes}` buys four things… a local model
> becomes genuinely replayable; a cloud model becomes at least **diffable**."*

**The factual claim is correct. The conclusion drawn from it is not.** Findings, one by execution.

### 4a · The transport SILENTLY DROPS both `seed` and `top_p` — executed, not read

`sdks/python/loreweave_llm/models.py:134-172` declares `StreamRequest` with no `seed` field, no `top_p`
field, and `model_config = ConfigDict(populate_by_name=True)` (`:137`) — no `extra=`, so Pydantic v2's
default `extra='ignore'` applies. Probed:

```
fields: ['chat_template_kwargs','max_tokens','messages','model_ref','model_source',
         'previous_response_id','reasoning_effort','stateful','stream_format',
         'stream_job_id','temperature','tool_choice','tools','trace_id']
StreamRequest(..., top_p=0.9, seed=42).to_request_body()
  -> {'model_source':…, 'model_ref':…, 'messages':…, 'temperature':0.0, 'stream_format':'openai'}
```

Both are accepted without error and both vanish. Two consequences:

- **`top_p` is already being set and already being dropped in production.**
  `services/chat-service/app/services/stream_service.py:381` and `:2086` both do
  `request_kwargs["top_p"] = gen_params["top_p"]` and then construct `StreamRequest(**request_kwargs)`.
  It never reaches the wire. **§0.13.3 names `top_p` as one of six fields to record as an input to the
  model call. It is provably not an input.** Recording it would place in the record a parameter the
  model never received — manufacturing precisely the class §0.13.1 lists as *"unrecorded parameters"*,
  in its inverse and more dangerous form: a **mis-recorded** one, which a replay would treat as
  authoritative.
- **A seed added at the caller will be swallowed with no error.** The clause's prescription ("record
  `seed`") is one boundary short of the change that would make a seed exist. A record can only be
  trusted if what it names actually reached the callee.

### 4b · Production is already greedy, so the seed's job is already done — by temperature

`sdks/python/loreweave_llm/models.py:147` — `temperature: float = 0.0`, and
`stream_service.py:370-372` states the invariant: *"Build kwargs sparsely so None values don't override
SDK schema defaults (StreamRequest.temperature defaults to 0.0…)"*. §0.12 concurs at
`ARCHITECTURE.md:808`: *"no seed on the chat path, **temperature 0.2 in the POC against 0.0 in
production**."*

**A seed controls the sampler's RNG. At temperature 0 the sampler is argmax and consumes no
randomness.** So on the default production path a seed changes nothing. What still varies at
temperature 0 is exactly what a seed cannot fix: floating-point non-associativity under varying batch
composition, continuous batching and KV-cache reuse, MoE expert routing, kernel/driver/build
differences, quantisation, and prompt-cache hits versus misses. The seed addresses the one source of
model non-determinism this product has already eliminated, and none of the sources that remain.

### 4c · "A local model becomes genuinely replayable" is over-claimed

`services/provider-registry-service/internal/migrate/migrate.go:14,40,90` —
`provider_kind IN ('openai','anthropic','ollama','lm_studio')`;
`sdks/python/loreweave_llm/reasoning.py:62` — `_LOCAL_KINDS = {"lm_studio","ollama","llama_cpp","vllm","openai_compatible"}`.

- **`anthropic`**: the Messages API exposes no `seed` parameter. For this provider kind the recorded
  field is permanently null, and §0.13.3 does not check this — the same "checked, not assumed" standard
  it applies to its own repository is not applied to the providers it proposes to seed.
- **`openai`**: `seed` exists and is documented as *best-effort*, paired with `system_fingerprint`
  precisely because the vendor does not guarantee reproducibility. "Diffable" is the right word; the
  clause uses it, and then also claims detection value the field cannot underwrite.
- **`ollama` / `lm_studio`**: genuinely seedable, and genuinely reproducible **only** under fixed
  batch size, fixed parallelism, fixed KV-cache/prompt-cache state, fixed quantisation, fixed GPU
  layer split and the same engine build. None of those are inputs the clause proposes to record, and
  several are host properties `code_revision` does not cover.

### 4d · The record's model identity is a mutable pointer, not a content address

Layer A (`:116`) demands inputs be *"named and **content-addressed**"* — `manifest_revision`,
`policy_revision`, `budget_revision`, `code_revision`. §0.13.3's record then names **`model_ref`**,
which is a UUID (`sdks/python/loreweave_llm/models.py:140`; `chat-service/app/db/migrate.py:9`)
resolved through `provider_client.py:13-14` to a mutable row. The upstream model name is user-editable
at runtime — `provider-registry-service/internal/api/mcp_server.go:510` declares
`provider_model_name` (*"the upstream provider's model name (e.g. gpt-4o, claude-3-5-sonnet)"*), `:584`
and `:641` update `user_models` in place. **The same `model_ref` can point at different weights on two
different days, and the record cannot tell.** The clause applies content-addressing to four artefacts
it controls and a bare pointer to the one input that dominates the output.

### 4e · Two inputs that DO reach the wire are absent from the proposed record

`reasoning_effort` (`models.py:153`) and `chat_template_kwargs` (`:154`) are forwarded to the provider
and materially change the output distribution — the SDK's own comment (`:125-131`) says thinking left
on *"silently burn[s] the output budget and the prose/JSON comes back empty."* Neither appears in
§0.13.3's six-field record. The proposed input set is incomplete against the transport schema sitting
one file away.

### 4f · A path where the prompt is not the client's to hash

`models.py:169-170` — `stateful: bool = False`, `previous_response_id: str | None`, documented at
`:163-168` as *"stateful `/v1/responses` routing… the server holds the prior context"*, live in
`stream_service.py:2078-2081`. On that path, a `prompt_hash` over the client-sent messages is **not** a
hash of the model's input; the rest lives on the provider's server, under an opaque id. §0.13.3's first
purchase — *"prompt drift becomes **detectable**"* — is false on this path by construction, and the
clause does not name it as an effect-quarantine seam.

**What the seed is worth:** on `openai`, a weak diffing aid. On `anthropic`, nothing — the parameter
does not exist. On local kinds, real value **only** after temperature is deliberately raised, the
transport is widened, and a set of host-level inputs the clause does not enumerate is pinned. Today,
recording it as prescribed would put a field in the record that never left the process — and alongside
it `top_p`, which provably does not. **A record that names inputs the callee never received is worse
than one that names none: the first is a false attribution, the second an honest gap.** That is §0.13's
own indictment of the CP-0 recorder (`:161-163`, `manifest_revision` *"accepted by the recorder and
**never supplied by any caller**"*) — reproduced by §0.13.3's own prescription.

---

## 5 · Opportunity cost

**The facts.** §0.13 adds P7 and P8 (`RUNSTATE:56-57`) and two checkpoint items:
`RUNSTATE:1165` item **1.8** (four parts: `NarrowingRule` becomes data not a closure;
`manifest_revision` becomes a recorded content hash; the purity boundary is named and gate-enforced;
the narrowing log becomes idempotent) → **CP-1**, and `RUNSTATE:1192` item **2.9** (the replay gate:
`policy_revision`, `code_revision`, `prompt_hash`, per-cache-block hashes, `seed`) → **CP-2**.

**State of play at the moment of insertion.** The *same* PO decision block, `RUNSTATE:1096`, exists to
unblock CP-1 by moving four items **out** of it (V-LIVE A–D, the β roster, 1.3's live measurement,
M4's "refuses to boot"), and records at `:1119`: *"**What CP-1 therefore closes on:** items 1.1, 1.2,
1.4, 1.5, 1.6, 1.7… **The last open item is the P4 fix's own verification**."* CP-2 is entirely `⬜`
(`:1188-1196`).

**The case FOR scope creep.** A checkpoint one verification from closing had a four-part build item
added to it, in the same decision that shed four items to get it there. The net motion of CP-1's scope
is not obviously downward. The justification is a cheapness claim — `:1165` *"the **CHEAP** moment is
now, before CP-4 admits a row… Retrofitting a revision id onto records that already exist is the CP-0
lesson in miniature"* — but *cheap* is asserted, not costed, and the clause's own history is the
counter-evidence: item 1.8 part 3 ("the purity boundary is named and gate-enforced") is a property
spanning the import graph, which is the shape `RETROSPECTIVE-CP0.md:88-90` names as the scoping failure
that cost ten rounds: *"**Scope a checkpoint to what one person can hold in view.** … If a property
spans five files, it belongs to the layer that makes it structural — not to a checkpoint that retrofits
it."* And §0.13's motivating argument — the CP-0 re-attribution — is defective on four independent
counts (§2 above), so the *case* for the addition is weaker than the addition's cost. Add finding 0:
the clause's insertion silently deleted a section and orphaned thirteen references, a cost paid
immediately and not by CP-1.

**The case AGAINST.** The two properties are real and, crucially, **measured broken, not theorised**:
`RUNSTATE:57` — P8 *"measured on the NEW package 2026-08-05: `assemble` called twice at one pass writes
the narrowing twice. **Third recurrence of the F-48 class, in a third file**"*. That is a live defect in
CP-1's own deliverable, found by looking; declining to fix it because a heading is nearly closed is how
a third recurrence becomes a fourth. The `NarrowingRule`-as-closure point is structurally correct and
timing-critical in the strict sense: a `Callable` has no content identity, so **no** `policy_revision`
can ever exist while it stands, and the number of records to retrofit grows monotonically from here.
The genus argument stands on its own without CP-0: P1–P6 (`RUNSTATE:50-55`) are demonstrably all
disclosure properties, and *"not one says 'do the same thing twice'"* (`:60-61`) is true on inspection.
And 2.9 lands in a checkpoint that has not started — no creep there at all.

**Which is stronger: scope creep, but narrowly, and not for the usual reason.**

The strongest anti-creep argument is the cheapness claim, and **the clause's own evidence contradicts
it**. The `seed` half of 2.9 is not cheap-now-expensive-later; §4 above shows it is **not implementable
now at any price** — the transport drops it, production runs greedy, one provider kind has no such
parameter, and `model_ref` is not a content address. Meanwhile the parts that genuinely are
cheap-now — P8's idempotence and `NarrowingRule` as data — need neither §0.13's determinism thesis nor
its CP-0 re-attribution to justify them. They are justified by `RUNSTATE:57`'s measurement alone.

So the clause bundles a **measured defect that should be fixed on its own evidence** with a **theory
that does not carry** and a **prescription that cannot execute**, and files the bundle against a
checkpoint that was one verdict from closing. That is scope creep dressed as architecture — not
because the work is wrong, but because the architecture argument is doing no load-bearing work for the
part of the bundle that is right, and is actively wrong about the part that is not.

---

## What survives

- **P7 and P8 as properties** — sound, and P8 is measured broken on the new package.
- **§0.13.1's ten-source table** — a genuine, bounded inventory; the honest core of the clause.
- **§0.13.2 layers A–C and E** — input closure, effect shell, effect quarantine, declared determinism
  class. E's symmetry argument (`:135-137`, *"C-13 requires every tool to declare `re_runnable`, while
  the runtime declares nothing"*) is the best sentence in the clause and needs none of the CP-0 story.
- **The observation that P1–P6 are all disclosure** — true on inspection, and sufficient on its own.

## What does not

- **The purpose argument.** Determinism buys power and debuggability, not attribution. Three named
  confounds survive it, one of which (measurement non-equivalence) is CP-0's actual documented cause.
- **§0.13.4's re-attribution.** Wrong about what the retrospective said; cites a number no round
  produced; re-labels a closed disclosure defect; and conflates *deterministic* with *input-invariant*
  in the sentence that carries the whole inference.
- **§0.13.3's seed prescription.** One of its six fields provably never reaches the model, `seed`
  itself would be swallowed by the same boundary, production is greedy, one provider kind cannot accept
  it, two live inputs are missing from the list, and one live path puts the prompt beyond the client's
  reach.
- **The clause's standing to make the argument at all**, until finding 0 is reckoned with: a section
  narrowed silently, and the index still says the list is complete.

*One inherited note, recorded so it is not mistaken for new damage:* the throughput risk at `:206-208`
(*"a phase that admits fewer than it retires is a red flag"*) is contradicted by §6.3 at `:1167-1169`
(*"**cannot fire**, because §1 says the plan deletes nothing and retirements are structurally zero"*)
and by `RUNSTATE:101` (*"The `≈13 admissions/week` throughput target stays withdrawn"*). That text is
byte-identical to `HEAD~1`'s §0.3 and predates this clause — but it now reads as part of §0.13.4, which
is finding 0's cost made concrete.
