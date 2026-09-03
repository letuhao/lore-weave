# RT-0.13 — falsifiability red-team of §0.13, P7, P8, CP-1.8, CP-2.9

> **Angle:** is this clause a *criterion* or a *slogan*? Attack only. No fixes proposed.
> **HEAD frozen at `4ec3f2a83318d0343c14c31bdd5645619fd9e16d`** (`git rev-parse HEAD`, verified before
> and after). No tracked file other than this one was edited. Author's commit messages not read.
>
> **Subject:** `ARCHITECTURE.md` §0.13 (:70–:208) · `2026-08-04-agent-runtime-RUNSTATE.md` P7 (:56),
> P8 (:57), CP-1.8 (:1165), CP-2.9 (:1192).

---

## Verdict

**§0.13 is a criterion in three places and a slogan in four.** The determinism *diagnosis* is real and
mostly verified against code (see §7 — I tried to break seven factual claims and six held). The
*criteria* built on top of it are not yet criteria:

| | claim | status |
|---|---|---|
| **F1** | layer A names "everything that affects the surface" — and the same clause, 40 lines later, names something it omits | 🔴 self-contradictory |
| **F2** | P7's cited evidence measures a different proposition than P7 states | 🔴 misattributed |
| **F3** | P7 cannot be falsified at n = 1, structurally — and the table header still says "six" | 🔴 not falsifiable as advertised |
| **F4** | the P7 test cannot be written today; five of its six inputs exist in zero non-doc files | 🔴 unwritable |
| **F5** | "below the model call" is undefined, and the boundary is undecidable for the surface path that produced the founding defect | 🔴 slogan |
| **F6** | "Enforced by the membrane gate, which already walks the import graph" — **executed, green on all four ambient sources**. Fourth instance of §6.1's exact defect | 🔴 **same shape as §6.1's false rows** |
| **F7** | DRIFT does **not** need "the record alone", and one of its inputs is fixed at container-start from `os.environ` | 🔴 not checkable as stated |
| **F8** | "the record is idempotent" is true, false, and deliberately false at three sites in one file at this commit | 🔴 undefined |
| **F9** | the artifact P8 was measured on has no reader, no persistence and no production call site | 🟡 measurement real, subject absent |
| **F10** | three sentences in §0.13 are unfalsifiable **by construction** | 🔴 |

---

## 1 · P7 — "the surface is a FUNCTION of its recorded inputs"

### F1 — layer A's enumeration is refuted by §0.13.4, forty lines below it

`ARCHITECTURE.md:116-118` (layer A):

> **A · Input closure.** *Everything that affects the surface* is named and content-addressed:
> `manifest_revision`, `policy_revision`, `budget_revision`, `code_revision`.

`ARCHITECTURE.md:156-157` (§0.13.4), the clause's own headline evidence:

> `budget_names_by_tokens` was query-dependent — **87 candidate tools for one message and 101 for
> another**

The **message** is not in the list of four. Neither is the conversation history, the pass number, nor
the prior completions. A set that calls itself *everything* and excludes a term the same section
proves is load-bearing is not an input closure; it is four of the inputs.

### F2 — the evidence attached to P7 does not measure P7

`RUNSTATE:56` cites *"Legacy's own surface is query-dependent (87 vs 101 candidates for two
messages)"* as the measured violation.

**That is not a violation of "the surface is a function of its recorded inputs."** A function of
`(manifest, policy, budget, code, message)` returns 87 for one message and 101 for another and remains
a function. The observation demonstrates **input under-specification** (F1), which is a defect in
layer A's list — not non-determinism in the runtime. The number is true and it is filed against the
wrong proposition.

This is the shape the same RUNSTATE flags on itself at `:122-128` (*"I re-attached a true count to the
wrong cause"*, `instrument.py`'s corrected attribution note). It has recurred in the row that was
written to close the genus.

### F3 — P7 is not falsifiable at n = 1, and the header was not updated

`RUNSTATE:36` still reads **"In its place: six invariants, each falsifiable at n = 1."** The table
immediately below it (`:48-57`) now holds **eight**. P7 and P8 inherited an n = 1 guarantee that was
asserted of a different, smaller set and never re-tested against them.

For P1–P6 the guarantee holds because each counter-example is **contained in one artifact**: one
advertised/withheld pair with no registration (P1); one row carrying `source_inferred` (P2); one
terminal path with no outcome (P3).

**P7 is a universally-quantified claim over *pairs*.** "X is a function of Y" is falsified by
`(y, x₁)` **and** `(y, x₂)` with `x₁ ≠ x₂`. No single record can contradict it. Falsifying P7 requires
two records with **byte-identical recorded inputs** and differing surfaces — and nothing in the design
guarantees the corpus contains such a pair. Under §0.12's own description of the corpus
(`ARCHITECTURE.md:807-809`: one dogfooding user, three rows of feedback), an input collision across
the full closure (manifest + policy + budget + code + **message**) is unlikely to exist at all.

So P7 is not "falsifiable at n = 1". It is falsifiable at n = 2-with-a-collision, and the collision is
not an event the system is built to produce.

*(The replay framing at `RUNSTATE:56` — "replaying the recorded revisions reproduces the recorded
surface" — converts the pair into one record plus one re-execution. That is a legal rejector under
§0.12. It is also not what §0.13 says: see F7 for why re-execution from "the recorded revisions"
cannot be performed.)*

### F4 — the test cannot be written today. What it needs, and what is absent

**How I searched:** `git grep -l "<term>" -- ':!docs'`, per term, at frozen HEAD.

| input P7 needs | non-doc files containing the term |
|---|---|
| `policy_revision` | **0** |
| `budget_revision` | **0** |
| `code_revision` | **0** |
| `reads_ambient` | **0** |
| `determinism_class` | **0** |
| `prompt_hash` | 4 hits, **all unrelated** — `contracts/migrations/per_reality/0003_event_audit_table.up.sql:56`, `services/knowledge-service/app/routers/public/projects.py:66,750,751` |
| `block_hashes` | 6 hits, **all unrelated** — translation-service segmentation |
| `manifest_revision` | 1 file: `services/chat-service/app/services/instrument.py:319` (parameter), `:339-340` (written **only if not None**) |

`manifest_revision`'s single production call site is
`services/chat-service/app/services/stream_service.py:6910-6913`:

```python
_advertised.record_pass(
    _adv_ev.get("names") or [],
    tool_choice=_adv_ev.get("tool_choice"),
)
```

No `manifest_revision=`. **RUNSTATE's claim is confirmed by execution of the search, not by reading.**

**And the input side has exactly one possible value.** `contracts/agent-runtime-manifest.json` is:

```json
{ "manifest_version": 1, "contract_version": "1.0.0", "declarations": [] }
```

A `manifest_revision` computed today hashes a constant. The membrane gate's own
`_manifest_drift` docstring already concedes the analogous point for M1
(`scripts/agentruntime-membrane-gate.py:250-252`: *"When CP-4 admits the first declaration this
comparison gains a real right-hand side"*). For P7 the same fact is fatal in a way it is not for M1:
**the independent variable cannot vary.** That is `docs/standards/non-vacuity.md` **NV-2** verbatim —
*"the thing is structurally incapable of the state that would fail it"* — and NV-2's tell (`:51`) is
*"you cannot describe, concretely, an input that reddens it."* I cannot.

**Answer to the question as asked:** the exact test would be

> take two turn records with identical `{manifest_revision, policy_revision, budget_revision,
> code_revision}` and assert their `advertised_tools` arrays are equal

and it cannot be written today because (a) three of the four columns exist nowhere, (b) the fourth is
never supplied, (c) the fourth would be constant if it were, and (d) per F1 the four are not the
closure, so two records agreeing on them proves nothing and two records disagreeing on the surface
refutes nothing.

---

## 2 · "Below the model call" — where is the boundary?

### F5 — the boundary is defined nowhere, and it is not decidable by inspection

`ARCHITECTURE.md:75-76`:

> **Below the model call, the same inputs produce the same surface** … Above the model call, nothing
> is promised.

Searched §0.13 (`:70-208`) for a definition of "below". There is none. Layer C (`:124-125`) says the
seams are "named" and "the record marks where determinism ends" — a *future* artifact, not a
criterion, and it is stated as a requirement on the reader (F10b).

**The function I cannot place — and it is the one the whole clause exists for.**

`failure_suppress` in `services/chat-service/app/services/stream_service.py`:

| | site | what happens |
|---|---|---|
| declared | `:1935` | `failure_suppress: set[str] = set()` |
| **written** | `:3755`, `:4268` | `failure_suppress.add(c["name"])` — `c` is a **model-emitted tool call** |
| **read as a narrowing** | `:2130-2131`, `:2212-2216` | `{"tool": t, "stage": "failure_breaker", …}` — removes the tool from the pass-N surface |

The surface offered on pass N is a function of the model's completions on passes < N. Is
`failure_breaker` **below** the model call (it is not the model call; it builds the surface) or
**above** it (its inputs are model output)? Both readings are defensible from the text, and the text
supplies no tiebreak. The same question applies verbatim to `REPEAT_READ_CAP` (`:524`, `:4303`), to
the one-shot suppressor (`:2200-2205`) and to the rail gate (`:2206-2211`).

**This is not academic — it decides whether the mechanism covers its own motivating case.**
§0.13.3 (`:143`) proposes recording

```
{model_ref, seed, temperature, top_p, prompt_hash, block_hashes}
```

Every term is **prompt-side**. No completion, no completion hash. So a replay holds the *input* to the
model call and nothing of its *output* — and therefore cannot reconstruct any pass ≥ 2.

**Arm E — the founding defect, §0.1 (`:62-66`) — is a mid-turn deletion, i.e. a pass ≥ 2 event.** The
input closure as specified cannot reproduce the one turn the clause was written about.

**Second unplaceable case, same finding.** `record_surface_withheld`
(`services/chat-service/app/services/instrument.py:254-266`) narrows through a **`ContextVar`**, chosen
deliberately (`:242-252`) because threading a parameter "failed twice". A `ContextVar` read is
process/request-scoped ambient state — §0.13.1's own row 2 (`ARCHITECTURE.md:104`) — sitting squarely
on the surface path, i.e. below the model call on any reading, and it is not `manifest.py`.

---

## 3 · The two replay questions — is DRIFT checkable with "the record alone"?

### F7 — no. Walked term by term.

`ARCHITECTURE.md:132`: **drift** *"does today's code produce the same surface for that input?"* —
needs: **the record alone** — used for **a CI gate, every commit**.

| input | recoverable from the record alone? | why not |
|---|---|---|
| **manifest content** | ❌ | a content hash is one-way. Recovering content from `manifest_revision` needs a hash→content store; **searched `scripts/`, `contracts/`, `services/chat-service/` — none exists.** If it were a git blob id it would resolve, but CP-1.8 (`RUNSTATE:1165`) specifies *"a content hash"*, and the manifest is **generated** (`manifest.py:181 generate`), so no commit is guaranteed to hold the state that ran |
| **rule set** | ❌ | CP-1.8 makes `NarrowingRule` data, which gives a *rule* content identity. The thing that must be addressed is the **sequence applied at that pass** — `assemble(pass_number=…, rules=…)` (`surface.py:126`) takes the sequence from its **call site**, per pass. Neither document says whether `policy_revision` identifies the rule library or the applied sequence. Those are different artifacts and only the second reproduces a surface |
| **budget** | ❌ **and this one is decisive** | `services/chat-service/app/services/tool_surface.py:50` and `:59`: <br>`HOT_SEED_TOKEN_BUDGET = int(os.environ.get("LW_HOT_SEED_TOKEN_BUDGET", "2000"))` <br>`RAIL_STEP_TOKEN_BUDGET = int(os.environ.get("LW_RAIL_STEP_TOKEN_BUDGET", "6000"))` <br>Read from `os.environ` **at module import**. The budget is a property of the *container*, not of the call. `code_revision` (the `GIT_SHA` from `build-stack.sh:14`, surfaced by `check_stack_freshness.py:38`) **does not determine it** — the same image with a different env var produces a different surface, at the same `code_revision` |
| **the message / prior completions** | ❌ | not named at all (F1, F5) |

So all four terms fail, and the third also **falsifies §0.13.1's first row** (`ARCHITECTURE.md:103`:
*"ambient … **yes**, confined to `manifest.py` **by accident**"*). At the scope the table declares
(*"in this system"* — and row 2 tags itself *"yes, legacy"*, so row 1 is not new-package-only), the
legacy surface path reads `os.environ` twice, **for exactly the quantity layer A wants to
content-address**.

### The second, structural objection to the drift gate

A gate that runs **every commit** against production records **cannot distinguish non-determinism from
an intended policy change.** Any deliberate edit to a narrowing rule reds it. The only available
resolution is to re-baseline — after which the gate certifies whatever today's code does. §0.13 names
no policy-change protocol and no way to tell "the code drifted" from "we changed the policy". A gate
whose red is routinely resolved by moving the expected value is NV-2 arriving on a delay.

### And neither replay question tests what P7 states

P7 is a **determinism** claim: *the same inputs produce the same surface.* Layer D offers **fidelity**
(record vs the code of that day) and **drift** (record vs today's code). Both are *reproducibility
across versions*. **Neither runs the same code twice.** The repo already owns the correct shape and
§0.13 does not cite it: `scripts/chaos/recover-replay-determinism.sh` — rebuild from the same events
twice, byte-compare, **with a bite arm** (`# Bite: rebuild a DIFFERENT seed's events … proves the
byte-compare distinguishes`) and an explicit strip of the wall-clock columns that would otherwise
fail it falsely. That last detail is the cost §0.13 does not price: a byte-compare over a surface
needs the list of fields that are legitimately allowed to differ, and nothing enumerates them.

---

## 4 · "Each stage declares its determinism class, and the gate enforces the declaration"

### F6 — executed. The nominated gate is green on all four ambient sources.

`ARCHITECTURE.md:121-122`:

> **B · Pure core, effect shell.** One named module may read ambient state; everything else receives it
> as a parameter. **Enforced by the membrane gate, which already walks the import graph.**

I loaded `scripts/agentruntime-membrane-gate.py` and ran its own `_violations_in()` against seven
synthetic probes. **Result — every one GREEN (no violation reported):**

| probe | §0.13.1 row it belongs to | gate |
|---|---|---|
| `import os` / `os.environ['X']` | row 1 — ambient, env | 🟢 **green** |
| `import time` / `time.time()` | row 1 — ambient, clock | 🟢 **green** |
| `import random` | row 1 — ambient, randomness | 🟢 **green** |
| `import uuid` / `uuid.uuid4()` | row 10 — identity generation | 🟢 **green** |
| `open(p).read()` | row 1 — ambient, filesystem | 🟢 **green** |
| iterate a `set` | row 2 — process state | 🟢 **green** |
| module-level mutable `dict` | row 6 — accumulated state | 🟢 **green** |

**Cause, and it is one line twice.** `scripts/agentruntime-membrane-gate.py:74`
`_STDLIB = set(sys.stdlib_module_names)`, then `:108` and `:119`:
`if _is_internal(mod, from_file=path) or _root(mod) in _STDLIB: continue`.
`ALLOWED_EXTERNAL` is `{}` (`:60`) — so the gate is **maximally strict against third-party imports and
maximally permissive against precisely the ambient set**, because in Python every ambient capability
(`os`, `time`, `random`, `uuid`, `secrets`, `socket`) is stdlib.

The last two rows are worse than a hole: `set` iteration and a module-level dict **are not imports**.
No import gate can ever see them. §0.13.1 lists them as rows 2 and 6 of the ten it claims to bound,
and layer B assigns the enforcement of that bound to a mechanism structurally blind to them.

**Is this the same shape as §6.1's earlier false rows? Yes — and it is the fourth instance in this
document, by the document's own count.** §6.1 (`ARCHITECTURE.md:1103-1146`) records:
"a bypass is a compile error" (false — no type checker runs); then a five-row *"what is actually
enforceable"* table of which rows 1, 2 and 4 were false (`:1119-1123`); then, at `:1135`, layer 2
described a repo-wide scan that nothing performed — annotated in place as *"A capability written as
though it existed — **the third instance in this one clause**"*.

§0.13.2 B is the fourth, and the tell is the word **"already"**. It is true of the *walk* and false of
the *check*. The gate already walks imports; it has never classified one as ambient, and nothing in it
could.

### What a static checker in Python can and cannot see

| can see | cannot see |
|---|---|
| `import` / `from … import` statements | `set`/`dict` iteration order under `PYTHONHASHSEED` |
| module-level name bindings | mutation of a caller-owned argument |
| a syntactically identifiable direct call | a `ContextVar` read (`instrument.py:254`) |
| construction sites of a named type (`:155-162`) | `getattr(mod, name)()` |
| | **anything behind a `Callable` parameter** |

That last row kills the declaration for the one function that most needs it.
`SurfaceAssembler.assemble` (`services/chat-service/app/agentruntime/surface.py:126`) takes
`rules: Sequence[NarrowingRule]`, and `NarrowingRule.keep` is
`Callable[[dict], bool]` (`:55`). **The purity of `assemble` is a property of its arguments, not of
its body.** No static checker can classify it. CP-1.8's *"`NarrowingRule` becomes data, not a
closure"* (`RUNSTATE:1165`) buys content identity; it does **not** buy checkable purity unless the
predicate language is closed and total, which CP-1.8 does not say and §0.13 does not mention.

The gate's own module docstring already states the honest version of this limit
(`:34-43`: *"Static imports only … A gate that claimed otherwise would be the more dangerous thing: a
check that reports safety it does not have."*). **Layer B makes exactly the claim that paragraph
refuses.**

### Two more, smaller

- **The repo already has a purity gate and §0.13 does not cite it.**
  `scripts/crate-purity-gate.py` enforces *"a law must not be ABLE to read a file"*. Its design notes
  (`:14-45`) record that a single-rule version was **killed in review**, and that purity had to be
  reduced to **capability reachability** (R3, *"no I/O-capable std path in src/"*) across four rules —
  and it is tractable only because Rust declares its dependency closure in `Cargo.toml`. Python has no
  equivalent. The precedent §0.13.2 B most resembles is the one that shows the cost, and it is unquoted.
- **`effectful` is already taken, on a different axis.**
  `scripts/eval/run_discoverability_scenario.py:197, 289-291, 699` uses `effectful` to mean *a
  non-read, write-committing tool call*. §0.13.2 E introduces `effectful` as a **determinism** class.
  Same word, two axes, one repo — the exact `audit`-means-two-things collision recorded at
  `docs/standards/non-vacuity.md:204-207`.
- **The symmetry argument rests on an unbuilt clause.** `ARCHITECTURE.md:135-136`: *"C-13 **requires**
  every tool to declare `re_runnable`, while the runtime declares nothing."* `git grep re_runnable`
  returns **docs only** — zero non-doc files. The asymmetry is between two things, neither of which is
  implemented; the present tense is doing work the code does not.

---

## 5 · P8 — "the record is idempotent". Under what operation, observed where?

### F8 — undefined, and the repo already answers it three ways in one file

`RUNSTATE:57` — *"the record is idempotent — writing the same fact twice leaves it unchanged"*. It
binds neither the **operation** nor the **observation point**. At frozen HEAD, both matter, because
`services/chat-service/app/services/instrument.py` contains three sites with three different answers:

| site | behaviour | verdict |
|---|---|---|
| `narrowing.py:81-82` — `NarrowingLog.record` | `self.entries.append(...)`, unconditional | ❌ **not idempotent** — this is what P8 measured |
| `instrument.py:371-374` — `record_withheld` | dedupes on `(tool, stage, len(self._passes))` | ✅ **idempotent** |
| `instrument.py:314-341` — `record_pass` | appends, `"pass": len(self._passes) + 1` | ❌ **deliberately not** — `:273`: *"One entry per model pass, appended, **never replaced**. The founding defect … is a tool that was offered on pass 1 and silently deleted before pass 2; a recorder that keeps only the latest state cannot show it"* |
| `instrument.py:474`, claim at `:495-496` — `segment_merge_sql` | *"**idempotent** — writing the same recorder's state N times leaves the array identical to writing it once"* | ✅ **idempotent, at the database** |

So *"the record is idempotent"* is, at one commit, **true in the database, true for legacy withheld,
false in the new log, and intentionally false for legacy passes** — where making it true would destroy
the artifact that motivated the entire run. P8 has no truth value until "the record" is bound to one of
these, and one binding is a regression.

### The prescribed mechanism contradicts P8, twenty lines above it

`ARCHITECTURE.md:88-91`:

> **We already had this pattern and used it once.** CP-3.1 specifies *"plans table — SPEC versioned +
> hashed, STATE **event-sourced**"* — content-addressed input plus an **event log**, exactly the
> mechanism below.

An event log is append-only. Appending the same event twice is **two events, by definition** — that is
what an event log is *for*. `NarrowingLog`'s own docstring says it is one
(`narrowing.py:72-77`: *"Everything withheld during one turn, **in the order it was decided**"*), and
`record_withheld`'s docstring says the same of a narrowing (`instrument.py:355-357`: *"A narrowing is
an **EVENT**"*). §0.13 endorses event-sourcing as the mechanism and P8 requires the record to be a
**state**. Neither document notices, and CP-1.8 (`RUNSTATE:1165`) ships both in one line: *"the
narrowing log is idempotent"*.

### F9 — the subject of the measurement has no reader

**How I searched:** `git grep -rn agentruntime -- services/chat-service/app --include=*.py`, excluding
the package itself. **Two hits, both string literals:**

- `services/chat-service/app/db/migrate.py:368` — `CHECK (runtime_variant IN ('legacy','agentruntime'))`
- `services/chat-service/app/services/instrument.py:100` — `RUNTIME_AGENTRUNTIME = "agentruntime"`

**Nothing imports `app.agentruntime`.** `NarrowingLog` has no persistence path, `Surface` reaches no
wire, `SurfaceAssembler` has no production call site. P8's *"measured on the NEW package"* measured a
Python list append in a package on no request path.

The measurement is legitimate under §0.12 (*a failure in test is information*). But P8's wording names
**the record**, and for the subject it was measured on there is no record — no column, no reader, no
merge expression, nothing that could be observed to be idempotent or not. Compare `segment_merge_sql`:
the legacy path has an actual record, and an actual idempotence property, and a docstring
(`:487-491`) enumerating the two prior wrong behaviours. The new package has a list.

---

## 6 · Unfalsifiable by construction

Three sentences in §0.13 are true in a way no observation could contradict.

**(a) "Above the model call, nothing is promised."** (`:76`) — a universal exemption whose scope is set
by an undefined boundary (F5). Because the clause supplies no independent test for which side a
function is on, **any observed non-determinism can be relocated above the line after the fact.** The
predicate that grants the exemption is the same judgement that would be under test. This is the load-
bearing one: it makes the whole clause unrefutable by any single measurement, because every refutation
has an escape.

**(b) "the record marks where determinism ends. A reader must not have to infer the boundary."**
(`:125`) — a requirement stated about a *reader's experience*. There is no artifact whose state could
contradict it and no gate that could report on it. It is a good intention in the grammatical position
of a criterion.

**(c) "The gap is bounded, not guessed — ten ways a substrate stops being a function."** (`:99`) — the
table has ten rows, no derivation, no source and no closure argument. Nothing could show an eleventh is
missing, so "bounded" cannot be wrong. A candidate eleventh, enough to show the bound was asserted
rather than derived: **collation.** `surface.py:180` sorts with Python's `sorted()` (codepoint order)
and `instrument.py:336` does the same; `segment_merge_sql` re-orders through
`jsonb_agg(e ORDER BY ord)` in Postgres. This repo's databases are `en_US.utf8`, not `C` — so a name
list sorted in Python and re-ordered by the database is a real way for a surface to stop being a
function of its inputs, and it appears in no row of the ten.

*(A fourth, weaker: `:136-137` — "We demanded more of the thing being anchored than of the anchor" —
is rhetoric resting on `re_runnable`, which exists in docs only. Not unfalsifiable, just unfounded.)*

---

## 7 · What I tried to break and could not

Stated because an attack report that only lists hits is not calibrated. **Search method in each row.**

| claim | check | result |
|---|---|---|
| *"`seed` appears nowhere on the provider path"* (`:141-142`) | `git grep -rn "seed" -- services/ai-gateway/src` | ✅ **0 hits.** Also: `services/provider-registry` does not exist as a path |
| *"`build-stack.sh` already computes `GIT_SHA` and labels images"* (`:117-119`) | `scripts/build-stack.sh:14,16,19`; `scripts/check_stack_freshness.py:38,204` (`org.loreweave.git_sha`) | ✅ true; "nearly free" is fair |
| *"identity generation — `uuid4` — present in the CP-0 recorder"* (`:112`) | `instrument.py:26` (`from uuid import uuid4`), `:308` (`self._segment = uuid4().hex[:12]`) | ✅ true |
| *"`NarrowingRule.keep` is an arbitrary `Callable`"* (`:106`) | `surface.py:55` | ✅ true |
| *"`manifest_revision` accepted by the recorder and supplied by no caller"* (`RUNSTATE:56`) | `instrument.py:319` vs `stream_service.py:6910-6913` | ✅ true |
| *"`assemble` called twice at one pass writes the narrowing twice"* (`:108`) | `narrowing.py:81-82`, and `surface.py:147` `_log_mark` deliberately counts only its own contribution | ✅ true of the log (see F8 for what "the record" means) |
| *"ambient confined to `manifest.py`"* (`:103`) — **new package only** | package-wide import scan: `manifest.py:23,54,227` (`os`, `os.environ.get`, `read_text`); `contract.py:17` imports `Path` but uses it only for `.parts` string-splitting at `:91` — **no filesystem read** | ✅ true **for `app/agentruntime/`** — ❌ false at the system scope the table declares (F7) |
| *"iteration order — partly handled (`sorted(names)`)"* (`:107`) | `surface.py:180`, `instrument.py:336` | ✅ true |

The **diagnosis** in §0.13.1 is largely verified. What fails is everything built on top of it: the
input closure (F1), the evidence attribution (F2), the falsifiability guarantee (F3, F4), the boundary
(F5), the enforcement (F6), the replay gate (F7) and the idempotence property (F8, F9).

---

## 8 · The clause measured against this repo's own standard

`docs/standards/non-vacuity.md` §3.1 asks five questions **in order**. Applied to P7 + CP-2.9:

| | question | answer |
|---|---|---|
| 1 | Can I state an input that reddens this? | **No.** Three of four revisions do not exist; the fourth is constant (`declarations: []`) ⇒ **NV-2** |
| 2 | Will it run on code written tomorrow? | **No.** Nothing imports `app.agentruntime` (F9) ⇒ **NV-3** |
| 3 | Did I just change a rule this checker depends on? | **Yes** — CP-1.8 changes `NarrowingRule`'s representation, on which `policy_revision` and therefore CP-2.9's whole input side depend ⇒ **NV-4** |
| 4 | Can the exemption carry a real reason? | The exemption is *"above the model call"* and it has no window at all (F10a) ⇒ **NV-5**, degenerate |
| 5 | Have I watched it fail? | **No.** No bite, no red, nothing to run ⇒ **NV-6** |

Five of five. And the register at `docs/standards/non-vacuity.md:145` already carries an **open**
NV-2 row — **#9, "replay-correctness is vacuous"** — on a different track, unclosed, un-engaged-with by
§0.13's layer D.

The standard's own summary of why this matters (`:29-32`) is the verdict on §0.13's current state:

> **A vacuous check is WORSE than no check at all.** … A vacuous check reports **coverage**. It is
> read as a settled question, it silences review, and it survives precisely because it is always green.

---

*RT-0.13 · adversarial review · HEAD `4ec3f2a83` · no fixes proposed, by instruction.*
