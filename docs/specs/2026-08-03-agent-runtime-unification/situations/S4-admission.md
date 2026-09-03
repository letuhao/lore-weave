# S4 — P3 Admission + the membrane · coverage interrogation

**Module:** `ARCHITECTURE.md` §3 (M1–M5), §6 (admission), read against §0.1, §0.3, §0.4, §0.5, §7.
**Method:** every claim below carries a `file:line` or a measured count from this repo. Where a prior
red-team report already measured a number it is cited rather than re-measured, and marked *(RT#)*.
**Verdict up front:** the membrane (M2) is the strongest thing in the design and is defensible by
construction. **Admission is not a design yet — it is one paragraph (§6) with four ordered steps, a
correct statistical warning, and no state machine.** Sixteen situations are enumerated below;
**four** are answered, **two** are partially answered, **ten** have no defined answer, and **two of
those ten are internal contradictions between §6 and §0.2 / §6.2 and Brick 4.**

---

## 1 · What admission exists to solve — grounded

The PO's sentence is *"only a surface with no noise can prove the new architecture works."* Admission
is the mechanism that keeps the surface noiseless. Four measured facts make that a real problem and
not a preference:

| # | the problem | measured | source |
|---|---|---|---|
| 1 | **The catalog is mostly dead weight already.** 192 of 315 live tools have never been called by the chat model; 225 have never once succeeded; 14 were called ≥5× with **zero** successes (worst: `glossary_propose_entity_edit` **0/101**) | 315 / 123 / 90 / 14 | RT4 §0, over `chat_messages.tool_calls`, 7,447 calls |
| 2 | **No registration path enforces a usable contract.** `require_meta` enforces exactly **two** fields — `tier` and `scope` — and its own docstring ships a carve-out: *"legacy glossary/knowledge tools predate `_meta` and are exempt"* | 2 of 12 P2 clauses | `sdks/python/loreweave_mcp/meta.py:11-14, 38-63` |
| 3 | **Membership in the surface is decided in ~7 uncoordinated hardcoded copies**, none compiler-checked: `TOOL_POLICY` (170), the FE bridge allowlist (6), `frontend-tools.contract.json` (11), `GROUP_DIRECTORY` ×2 languages, `ALWAYS_ON_CORE_NAMES`, `ALWAYS_HOT_WRITES`, `hot_domains` prefix pins ×12 skills | 7 copies | RT4 §1.1–1.3 items 3, 14, 17, 24, 27, 28 |
| 4 | **The one existing "manifest" is stale, tripled, hand-generated, and its ship gate fails open at four layers.** `contracts/tool-liveness.json` holds **223** tools against a live catalog of **315**; is byte-duplicated into three trees; its generator **runs nowhere in CI**; and `toolBlocked()` rejects only an explicit `executes:false` — of which there are **zero** (203 `true`, 13 `null`). See §6 | 223 vs 315; 3 copies; 0 blocks | `contracts/tool-liveness.json` (verified: 223 keys); `scripts/eval/tool_liveness/manifest.py`; `agent-registry-service/internal/api/liveness.go:66-84`; RT4 §0, §30, RT4-1b |

**So admission exists to solve exactly this:** a catalog where *registration* is nearly free, *removal*
is impossible, *membership* is decided in seven places, and the artifact that was supposed to be the
gate has never once blocked anything. That is a real and correctly-identified problem.

**And the membrane's answer to it is genuinely strong where it is strongest.** M2 — the new assembler
takes the manifest as its only catalog argument, enforced by an import-graph gate — removes the
*possibility* of the path rather than checking that it is unused. That is the correct shape and it is
the one property here that a future contributor cannot erode by accident. Nothing below disputes M2.

---

## 2 · Ground truth — the denominator admission must clear

Counted fresh for this report, not restated. Registration sites were counted per file and
de-duplicated on tool name.

| unit | count | source |
|---|---|---|
| **domain MCP tools registered in source** | **317** = 183 Python + 134 Go | Python `@…tool(name=…, meta=require_meta(…))` across 6 servers: composition **122**, knowledge **41**+2 admin, translation **12**, jobs **5**, lore-enrichment **1**. Go: glossary **58**, book **52**, provider-registry **13**, agent-registry **9**, catalog **2** |
| + gateway-local TS tools | **10** | `ai-gateway/src/mcp/ui-tools.ts` (7 `ui_*`) + `propose-edit-tool.ts:28` + `mcp-public-gateway` `confirm_action` / `invoke_tool` |
| + chat-service consumer-local meta-tools | **6** | `find_tools`, `tool_list`, `tool_load` (`tool_discovery.py:47,51,52`), `load_skill` (`skill_registry.py:297`), `workflow_list`, `workflow_load` (`workflow_runner.py:31,32`) |
| **tools served by `tools/list`** | **315** | `ai-gateway/src/mcp/handlers.ts:69-82` *(AUDIT §58)* |
| — of those, advertised / `visibility:"legacy"` | **202 / 114** | `scripts/deprecated-tool-scan.py` *(AUDIT §61)* |
| skills (`SkillDef`) | **12** | `services/chat-service/app/services/skill_registry.py:104-286` |
| seeded workflows *(= "rails"; there is no separate rails table)* | **12** (45–47 `steps[].tool` refs → **30** distinct tools) | 12 × `INSERT INTO workflows` at `services/agent-registry-service/internal/migrate/migrate.go:498…767` |
| **total P1 declarations** (§0.2: tool + skill + workflow are three kinds of one thing) | **339** on the wire · **357** counted at the registration sites | 315 / 333 + 12 + 12 |
| public-edge allowlist entries | **170** (`write_auto` 62 · `read` 61 · `write_confirm` 44 · `paid_read` 3) | `services/mcp-public-gateway/src/scope/tool-policy.ts:87-338` |
| FE bridge allowlist | **6** | `services/api-gateway-bff/src/tools/tools.controller.ts:24-31` |
| FE↔BE tool contract | **11** — **disjoint from the 6 above** | `contracts/frontend-tools.contract.json` |
| measured product tool-call throughput | **7,447 calls over ~18 weeks ⇒ ≈414 / week** | RT5 §1.1 (7,447 calls); *"first message ever 2026-04-03"* RT5:90, to 2026-08-04 |
| measured tool failure rate | **53.8 %** (4,010 / 7,447) | RT5 §1.1 |

**The three catalogs already disagree, and the gaps are the shape of the problem admission inherits:**

```
registered in source   317        composition:  122 registered
tool-liveness.json     223                       69 in tool-liveness
TOOL_POLICY            170                       55 in TOOL_POLICY
```

**≈147 registered tools are unreachable from the public gateway** — denied by absence and logged as
drift, per `tool-policy.ts:84-86`'s own stated intent (*"a NEW federated tool absent here is denied +
logged … until classified"*). Nobody classified them. **That backlog is admission, already running,
already failing** — and it is the closest thing to a measured admission rate the repo has (see §3.2).

`C1` (SPEC §1.3) states the catalog is **expected to reach thousands of tools**. Every number below
should be read twice: once at 339, once at 3,000.

---

## 3 · 🔴 THE THROUGHPUT ANSWER — the number §0.3 demands and never computes

§0.3 names the risk precisely — *"Admission is a throughput problem, not a gate problem… admission
rate must be reported per phase"* — and then attaches **no target rate**, no budget, and no
parallelism model. Computing it is the single most decisive thing this interrogation can do.

**Demand.** 339 declarations (357 counted at the registration sites) must clear the membrane before
the membrane becomes the ceiling. The design's own cadence reference is Anthropic's Opus 4 → Opus 4.5
step (§0.3), **≈6 months = 26 weeks**.

```
339 declarations ÷ 26 weeks  =  13.0 admissions per week
357 declarations ÷ 26 weeks  =  13.7 admissions per week
```

> ## **≈13 admissions per week — sustained, forever, per model generation.**
> **At 3,000 tools (C1) that becomes 115 / week. At a realistic 1 / week, the current catalog
> completes in 339 weeks ≈ 6.5 years — about thirteen model generations.**

**Supply — and this is where it breaks.** §6.3 sets the evidence bar itself: a ≤10 % claim needs **29
consecutive successes**, and §6.2 requires those runs be **solo** (*"the tool is the only thing on the
new surface"*), plus §6.4 adds an adversarial arm.

```
13 admissions/wk × 29 solo successes      =   377 solo turns / week   (floor, zero failures allowed)
                 × (+ adversarial arm)    ≈   754 solo turns / week   (realistic)

product's ENTIRE measured tool throughput ≈   414 calls  / week
```

> **Admission at a ceiling-avoiding rate needs 0.9×–1.8× the entire tool traffic this product has
> ever generated — and none of it can come from production, because a solo surface has one tool on it
> and no user session runs on one tool.** Every admission turn must be synthesised.

And the floor assumes zero failures. At the *measured* 53.8 % failure rate, the expected number of
trials to observe a first run of 29 consecutive successes is `1/(p²⁹·(1−p))` with `p = 0.462` —
**≈1 × 10¹⁰ trials.** The 29-success bar is therefore not a schedule constraint; for any declaration
that has not *already* been repaired, **it is unreachable in principle**, and §6 does not say so.

### 3.1 🔴 The one metric §0.3 attaches to the risk cannot fire

> *"a phase that admits fewer than it retires is a red flag, not progress"* — §0.3

§1 states the plan **"deletes nothing"**; §7 states the old runtime stays live *as the control group*.
Retirements are therefore **structurally zero**, so `admitted ≥ retired` holds unconditionally, at any
admission rate including zero. **The single number attached to the design's own tracked risk is
unfalsifiable by construction.** This is precisely the shape the repo has already recorded as
`enforcement-claims` rot and as `feedback_a_check_whose_control_and_seed_agree_is_theatre`.

### 3.2 The repo has already run a one-at-a-time admission process, and it has a 147-item backlog

`TOOL_POLICY` is not merely an allowlist — it is **a human-classified, one-tool-at-a-time admission
gate with a default-deny membrane**, i.e. the same mechanism P3 proposes, already live on the public
edge, with the same *"denied by absence"* property M1 wants. **It is therefore the only empirical prior
available for admission throughput, and it should be quoted in §0.3 instead of an estimate.**

Its record: **170 classified, ≈147 outstanding** — and its own source comments document three separate
multi-month misses discovered by audit rather than by the process:

- `story` — *"already a real, live GROUP_DIRECTORY domain on BOTH federation surfaces… it was simply
  never added to this PUBLIC-key allowlist"*, found 2026-07-08 (`tool-policy.ts:30-39`);
- `registry` — *"had NO Domain member and NO TOOL_POLICY entries — the exact same incomplete-rollout
  shape as the `story` gap above"*, found the same day (`:41-49`);
- `research` — added 2026-07-09, requiring a **new published OAuth scope** (`:50-55`).

> **The measured throughput of this repo's existing admission process is ~54 % coverage with a
> three-domain blind spot that took months to surface.** Projecting that onto 339 declarations under a
> *stricter* contract (12 clauses vs. `TOOL_POLICY`'s two fields) and a 29-success evidence bar is what
> §0.3's "tracked risk with a number attached" should actually contain.

**Ceiling Test:** admission as specified changes what the model **CAN DO** (a non-admitted declaration
is absent, not deferred), it is **not visible to the model**, and it is **not appealable by the model**
— it fails all three clauses of §0.3's own design rule. §0.3 grants an exemption only to P6. **P3 is
not P6.** The design acknowledges this in prose (*"the membrane can become a ceiling"*) and then
mitigates it with a metric that cannot go red.

---

## 4 · Situation coverage

| # | situation | answered? |
|---|---|---|
| A | a reference to a non-admitted declaration | ✅ **M5**, checked at generation |
| B | a non-compliant declaration tries to register | ⚠️ **M4** — *premise is Python-only*, see F8 |
| C | the new surface reaching the old catalog | ✅ **M2**, by construction. The strongest thing here |
| D | discovery leaking a legacy declaration | ✅ **M3**, with a stated red-able test |
| E | the consumer of a producer/consumer pair, admitted first | ✅ blocked by M5 / C-6 |
| 1 | **an admitted declaration must change** | ❌ **F1** |
| 2 | **the contract itself is amended by a failed admission** | ❌ **F2** — §6's own procedure |
| 3 | **a producer + consumer pair, together** | ❌ **F3** — §6.2 contradicts Brick 4 |
| 4 | **the same tool on both runtimes** | ❌ **F4** — invalidates §7's control group |
| 5 | **evidence for a rarely-called declaration; evidence expiry** | ❌ **F5** |
| 6 | **skills and workflows have no admission procedure** | ❌ **F6** — §6 contradicts §0.2 |
| 7 | **a third-party public key vs. an admitted tool** | ❌ **F7** |
| 8 | **bypassing admission** | ❌ **F8** — no independent definition of "admitted" |
| 9 | **manifest vs. running code** | ❌ **F9** |
| 10 | **admitted, then regresses in production** | ❌ **F10** |
| 11 | **admitted, then never used** | ❌ **F11** |
| 12 | **a rollback strands an in-flight plan** | ❌ **F12** |
| 13 | **provider down / catalog cache stale** | ❌ **F13** |
| 14 | **name collision across the membrane** | ❌ **F14** |
| 15 | **the runtime's own un-admitted primitives** | ❌ **F15** |

---

## 5 · Findings, ranked

### 🔴 F1 — An admitted declaration that must CHANGE has no procedure, and the obvious answers are all ceilings

**§6 defines exactly one transition: `built → admitted`.** §0.1 adds *"only a deploy changes what is
admitted"*. There is no `admitted → changed → ?` edge anywhere in ARCHITECTURE.md.

The question is not academic — **changing an admitted declaration is the primary repair action this
whole spec exists to enable.** C-4 (`accepts` provenance) owns the **57 %** identifier-failure class
and **189 of 315 declarations give no argument-source guidance** (§4). Fixing one means editing a
declaration's schema *after* it was admitted.

Undefined, and each candidate answer is bad in a different way:

- **evidence resets** ⇒ 29 more solo successes per repair ⇒ improving a tool costs the same as
  admitting one ⇒ §3's throughput number doubles, and the admitted set freezes at its first-draft
  quality. **A ceiling on the tools' own improvement.**
- **evidence carries** ⇒ the admitted-at bound (§6.3) is now attached to a contract that no longer
  exists, which is the thing §6.3 exists to forbid (*"never state a bound the run cannot support"*).
- **it depends on the change class** ⇒ someone must classify diffs (additive / narrowing / behavioural).
  SPEC R13.2 designs exactly that generator — **and ARCHITECTURE.md's M1–M5 does not include it.**

**M1's gate cannot detect the case at all:** it is *"manifest row count == admitted count"* — a
**count**. A contract change to an already-present row does not change the count.

**Cross-document damage:** SPEC R13.5 answers rename (add-new + `superseded_by` + sunset), but SPEC
Q14 already **killed** that model on measurement — *"54 tools declare `superseded_by`, pointing at
only 17 distinct targets… renames here are not renames, they are many-to-one CONSOLIDATIONS"*.
ARCHITECTURE.md supersedes only SPEC §1.4 and never reconciles Q14 with admission. **A consolidation
admits one declaration and must un-admit six.** No such operation exists.

**Needed:** a declaration-level revision key in the manifest; a diff classifier deciding which change
classes preserve evidence; an explicit consolidation operation (N un-admitted → 1 admitted, usage
history aggregating along the edge per Q14).

---

### 🔴 F2 — §6's own failure procedure invalidates every prior admission, and the design does not notice

> *"A tool that fails admission is not patched into compliance and re-run. The failure is the finding —
> it is data about the contract, and the contract is what gets amended."* — §6

Read literally, this is a ratchet with no ratchet-release:

1. declaration #31 fails admission;
2. the P2 contract gains clause C-13;
3. declarations #1–#30 were admitted against a contract that lacked C-13.

Two exits, both forbidden elsewhere in the same document:

- **grandfather #1–#30** ⇒ the manifest now holds two contract generations ⇒ *"only a tool built to
  the new architecture can load into it"* becomes false, and the surface is no longer noiseless —
  which is the entire premise of the empty runtime.
- **re-admit #1–#30** ⇒ the contract can never be amended without paying `30 × 29` solo runs, so in
  practice **it never gets amended** and §6's stated learning loop is dead on the first use.

**This is the highest-value finding because §6's procedure is the design's *intended* mode of
operation.** It is expected to fire often — the contract is explicitly a work in progress (C-4/C-5/C-6
are described as new in §4). The design has no contract-version field, no per-row `admitted_against`
stamp, and no re-admission queue.

**Needed:** `contract_version` on the manifest row + a stated policy for what an amendment does to
rows admitted under an earlier version, including whether it is a blocking backlog or an advisory one.

---

### 🔴 F3 — A producer/consumer pair cannot be admitted at all: §6.2 forbids what Brick 4 requires

**§6.2:** the admission run is **solo** — *"the tool is the only thing on the new surface besides the
runtime's own primitives. Zero noise, by construction, exactly as the PO requires."*

**§8, Brick 4:** *"one **two-step pair** where step 2 consumes step 1's `emits` (C-6) … the 61.8 %
class — the one no shape addresses. **Brick 4 is the one that matters most** … it should be built
early."*

**Brick 4 requires two declarations on the surface simultaneously. §6.2 forbids it.** These are 130
lines apart in the same file and neither references the other. The design's own most-important test
is unrunnable under its own admission rule.

The consumer-first direction *is* answered (M5 + C-6 make it unresolvable). Everything else is not:

- **Can the producer be admitted alone?** Its own success is observable, but the pair's value —
  `emits` → `accepts` binding, the thing §0.4 calls *"the one part of this design with no prior art"* —
  is unobservable in a solo run.
- **What is the admission order over the C-4/C-6 dependency graph?** Nobody computes that DAG today
  (189/315 declare no provenance at all), no topological ordering is specified, and **a cycle** (A
  emits what B accepts, B emits what A accepts) has no defined resolution.
- **Is a pair one admission or two, for the §0.3 rate metric?** Undefined, so the one reported number
  is not comparable across phases.

**Needed:** admission must have a *unit* larger than one declaration — an "admission set" with a
declared internal dependency closure — or §6.2's solo rule needs an explicit, bounded exception with a
noise budget.

---

### 🔴 F4 — The same tool is on both runtimes by construction, and admitting it CONTAMINATES the control group

§7's claim is load-bearing: *"That is not tolerated legacy. It is the control group,"* and the red
team's sharpest schedule finding was that a clean floor destroys the only thing the comparison can be
measured against.

**Topology, verified:** each provider service exposes **one** MCP server; ai-gateway federates ten of
them (`infra/docker-compose.yml:1082`); **both** consumers read that one federation — chat-service
(where the new runtime lives, §0) and `mcp-public-gateway` (which relays to ai-gateway,
`public-mcp.controller.ts:50-51, 290-291`).

**Therefore there is one implementation per tool, shared across the membrane.** But admission requires
*editing that implementation*: C-3 adds a `limit`, C-4 restructures arguments, C-5 removes the silent
substitution (`stream_service.py:1619-1623`), C-6 adds `emits`, C-7 re-shapes every error, C-12 adds a
fault locus.

> **Admitting a tool changes the tool. The old runtime serves the same object. The control group is
> contaminated by every admission — and it is contaminated *most* on exactly the declarations whose
> improvement the experiment is trying to measure.**

M3's membrane is one-directional: it stops the *new* surface reading the *old* catalog. **Nothing
stops the old surface serving the new declaration's behaviour** — indeed nothing *can*, short of a
fork. The design picks none of the three available options and does not acknowledge the choice:

| option | cost the design never states |
|---|---|
| fork under a new name | catalog doubles; the new name is absent from `TOOL_POLICY`'s 170-entry default-deny (→ F7); `superseded_by` edges multiply |
| version-negotiate per consumer | no mechanism exists; the federated catalog is **cached with a refresh timer**, so a change is not observable until restart *(RT4 §23)* |
| edit in place, accept contamination | §7's control-group claim is void, and with it the only stated way to prove the new runtime is better |

**And nothing detects drift between the two copies.** M1's gate compares the manifest to an admitted
count, not to what the provider actually serves.

---

### 🔴 F5 — Evidence for a rarely-called declaration is unobtainable, and evidence never expires

**Two independent holes.**

**(a) There is no traffic to gather 29 successes from.** 192 of 315 tools have **never** been called;
225 have never succeeded *(RT4 §0)*. The solo admission surface generates no organic traffic by
construction. And the standing acceptance instrument cannot substitute: the liveness matrix
**runs zero LLM turns for 214 of 224 tools** *(RT5-4)*, and the POC's arms *"were built from a live
catalog and are not reproducible today"* (DESIGN-HYPOTHESIS §4.3 item 5).

For a declaration called twice a week, 29 consecutive successes is **≥14.5 weeks of flawless
production traffic** — and at the measured 53.8 % failure rate it is never reached at all (§3).

**(b) §6.3 states a bound but is not a gate.** *"State the bound each tool was admitted at; never
state a bound the run cannot support"* is a **disclosure rule**. It sets no *minimum*. A declaration
admitted on 3/3 is admitted at ≤63.2 % — **worse than the 54.2 % production baseline the membrane
exists to beat.** As written, §6 admits anything as long as the label is honest.

**(c) Evidence has no expiry and no model binding.** §0.3's entire premise is that models change. A
declaration admitted on 29 successes against model *M* carries that stamp forever; nothing says the
evidence is re-earned against *M+1*, nor that the bound is even recorded per-model. RT5-7 makes this
worse: **the chat path has no `seed` and its temperature is unrecorded** — so an admission run is not
reproducible even against the same model.

**Needed:** a minimum admissible bound (not just a disclosed one); an evidence record keyed to
`(declaration, contract_version, model_ref)`; and a stated policy for declarations whose call volume
can never reach the bar — probably a distinct, *labelled* admission class rather than silence.

---

### 🔴 F6 — §6 admits tools. §0.2 and M1 say the unit is a declaration. Skills and workflows have no procedure

§0.2 is emphatic: *"Tool, skill and workflow are three kinds of declaration over P1–P6."* M1 puts
*"tools, skills and workflows in one manifest"*. M3's test seeds *"a legacy-only declaration of each of
the three kinds."* The membrane is consistently defined over **declarations**.

**§6 is titled "Admission — one tool at a time" and every one of its four steps is tool-shaped:** a
solo *live run*, `29 consecutive successes`, an adversarial arm over *"the tool's hardest argument"*.

None of it types:

- a **skill** *"adds no execution of its own"* (§0.2) — what is a solo live run of a thing that does
  not execute? What counts as a success?
- a **workflow**'s success predicate is `done_when`, *"a predicate over real state"* (C-8) — 29
  consecutive satisfactions of a state predicate is a different measurement entirely, and a workflow's
  members must already be admitted (M5), so its cost is `Σ members` before it can even start.
- the **12 seeded workflows** are re-seeded `DO UPDATE` on every deploy *(RT4 §25)* — a deploy-time
  upsert that rewrites 45 step references. Does a re-seed re-admit? Un-admit? Nothing says.
- and **the skill kind is already split across two homes**: the `skills` table seeds **5** rows
  (`migrate.go:381-387`) while `skill_registry.py` defines **12**, with bodies deliberately kept in
  code (DL-4). M1 puts skills in the manifest — so admission must first decide *which* of the two is
  the declaration, and the answer determines whether 7 skills are currently un-admittable.

**This gap directly inflates §3's number**: 24 of the 339 declarations have no defined admission
procedure at all, and the 12 workflows sit *downstream* of 30 tool admissions.

---

### 🔴 F7 — A third-party key and an admitted tool have no defined relationship, and the public allowlist becomes a fourth hand-maintained copy

`TOOL_POLICY` is a **170-entry hardcoded allowlist** and is **default-deny by absence** —
*"Any tool NOT in this table is denied by absence (H-E — default-deny unknown / fail-closed)"*
(`tool-policy.ts:8-10`). Nine OAuth scopes are **published** in the third-party vocabulary
(`services/auth-service/internal/api/oauth_meta.go:144-146`), and **keys are issued**, with a
per-`tools/call` audit row *(RT4 §17–19)*.

**§7 says the public edge is untouched, and stops there.** Both branches of F4 break it:

- **fork under a new name** ⇒ the new name is not in `TOOL_POLICY` ⇒ **denied and logged as drift** for
  every public key that reaches for it, and a new-runtime `domain` would need a **tenth published
  scope** that no issued key holds.
- **edit in place** ⇒ external clients receive a changed contract (a newly-required `limit`, a
  restructured `accepts`, a re-shaped C-7 error body) with **no version negotiation and no deprecation
  window in this path** — the exact break RT4 §1.2 identified as A9's own falsifier, arriving one
  admission at a time instead of all at once.

**And admission has no clause requiring a `TOOL_POLICY` entry at all.** So on day one of admission,
the manifest and the public allowlist begin diverging — a *fourth* uncoordinated copy joining the three
the audit already found. That is the failure this architecture was written to end, reproduced inside it.

**They have already diverged by 147** (§2, §3.2): 317 tools are registered, 170 are classified, and the
gap is not tracked anywhere as a number. Under §0.2's substrate the fix is nearly free and should be
stated as a clause — **`TOOL_POLICY` becomes a derived projection of the manifest** (`tier` and
`domains` are C-2 `scope` data the declaration already carries), which deletes the fifth
hand-maintained copy instead of adding one. That is the same "removes work rather than adding it"
argument §0.2 makes for skills and workflows, and it is the clause §6 is missing.

---

### 🟠 F8 — "Bypassing admission" is not defined as impossible, because "admitted" has no independent definition

M2 is a genuine construction argument and it holds: the new assembler cannot import the legacy
catalog, and an import-graph gate reds if it does. **But M2 governs where the catalog comes FROM, not
what may be put INTO the manifest.**

M1's gate is *"manifest row count == admitted count; drift reds CI."* **What produces `admitted
count`?** If it is derived from the manifest, the check is a tautology. If it is a second artifact,
that artifact is undefined — and it is the actual admission ledger. **Nothing in §3 or §6 requires the
solo-run evidence to be persisted as an artifact keyed to the manifest row.** Absent that, a
hand-added row and a 29-success admission are **indistinguishable by inspection**, which makes "bypass"
undetectable rather than impossible.

**Three in-repo precedents say this WILL happen:**

1. **The repo's only existing registration gate shipped with its bypass in its own docstring** —
   `meta.py:11-14`: *"legacy glossary/knowledge tools predate `_meta` and are exempt."*
2. **M4's stated premise is Python-only.** §3 says *"the existing `require_meta` chokepoint already
   panics on a missing tier."* True in Python (`meta.py:137` always validates). **In Go it is false:**
   `NewToolMeta` (`sdks/go/loreweave_mcp/meta.go:184-196`) builds the map and **does not validate**,
   and `RegisterTool` *"forwards straight to `mcp.AddTool` and does NOT validate meta"* — stated in the
   repo's own test header (`services/glossary-service/internal/api/mcp_meta_contract_test.go:9`).
   Verified counts: **137 `NewToolMeta` call sites** across 5 Go services vs **5 `MustValidateToolMeta`
   call sites in 4 services** — and **glossary-service, with 58 of the 137, calls it zero times**,
   substituting a per-service wire test. M4 extends a chokepoint that does not exist in one of the two
   backend languages.
3. **The precedent gate for exactly this job fails open.** `toolBlocked()` rejects only an explicit
   `executes:false`; there are **zero** such rows, so 12 workflows keep seeding against 30 non-existent
   tools and only warn *(RT4-1b)*.

**Needed:** an admission ledger that is a *separate artifact* from the manifest (evidence, bound,
model_ref, contract_version, date, owner), with the M1 gate comparing manifest ↔ ledger — so the two
can disagree, which is the only way the check is non-vacuous.

**And the repo already contains the exact pattern, fully worked, under the same word.**
`services/commit-service/src/admission.rs` mints `Admitted<D>` — **a proof token whose field is
private, so a caller cannot assemble one: an admission bypass is a *compile error*.** Because the
type system cannot cover everything, `scripts/ingress-admission-gate.py` covers the residue, and its
three rules are precisely the three bypasses P3 will face:

| the Rust gate's rule | the P3 equivalent it maps onto |
|---|---|
| `Admitted::admit` may be called from **one** sanctioned module — *"a second minter elsewhere would restore the very bypass IAS-D3 removed — silently, and with a name that reads like it did the right thing"* | one writer for the manifest: the generator. A hand-edited row is a second minter |
| `Admitted::unchecked` may appear only in tests/benches — *"in a service source file it is a bypass wearing the test escape hatch"* | the "temporary" admission for a demo, and the test fixture that becomes a fixture in prod |
| `features = ["test-util"]` may only be a **dev** dependency — *"would hand a shipped binary the unchecked mint … while every test stayed green"* | a build flag that admits the legacy catalog "just for the migration" |

P3 should copy this wholesale rather than invent. **M2 is the type half; the ledger + a minter gate is
the missing half**, and this repo has already shipped both halves once for a different subsystem.

---

### 🟠 F9 — Manifest vs. running code is unchecked; the repo has this exact bug today, unnoticed

M1 compares the manifest to an admitted count. M2 constrains the assembler's input. **Nothing compares
the manifest to what the provider services actually serve on `tools/list`.**

The precedent is already live and already wrong, **for all three declaration kinds at once**:

| kind | catalog says | code says | gap |
|---|---|---|---|
| **tool** | `contracts/tool-liveness.json` → **223** | **317** registered / **315** on `tools/list` | 92–94, **eval-derived not catalog-derived** *(AUDIT §60)*, byte-duplicated into **three** trees *(RT4 §30)* |
| **tool** (public) | `TOOL_POLICY` → **170** | 317 registered | **≈147 unreachable**, "denied + logged as drift until classified" |
| **skill** | `skills` table seeds **5** rows (`migrate.go:381-387`: `glossary`, `universal`, `knowledge`, `admin`, `plan_forge`) | **12** `SkillDef`s in `skill_registry.py` | **7 skills exist in code and not in the catalog** |
| **workflow** | 12 seeded, **30** distinct tools referenced | 30 of them dead *(RT4-1b)* | four-layer fail-open, §6 |

A manifest that disagrees with the code by 29 % — and a skills catalog that knows about 5 of 12 — is
the repo's existing steady state. **M1 must red on all four rows on day one, or it is the fifth copy.**

Two further gaps ARCHITECTURE.md does not carry, one of which SPEC.md already designed:

- **SPEC phase 1b** specifies *"CI reds on live-catalog ≠ snapshot with no migration entry."* That is
  the right gate. **It is not among M1–M5**, and ARCHITECTURE.md presents M1–M5 as the complete
  membrane.
- **The federated catalog is cached with a refresh timer** *(RT4 §23)*, so even a correct manifest and
  correct code can disagree *on the wire* for a whole cache window, with no signal.

**The precedent generator is not in CI, and that is how the 223-vs-315 gap got there.**
`scripts/eval/tool_liveness/manifest.py` — the sole producer of `contracts/tool-liveness.json` and its
two consumer copies — **runs nowhere in CI**; it is invoked by hand from a dated eval matrix. Only the
*byte-equality of the three copies* is tested (`chat-service/tests/test_tool_liveness.py`,
`agent-registry-service/internal/api/liveness_test.go`). **The repo tests that its manifest is
consistently copied and never that it is current.** M1's *"drift reds CI"* must therefore mean
*regenerate-and-diff in CI*, not *compare-the-copies*, and ARCHITECTURE.md does not say which.

**Also worth fixing while writing the generator:** `contracts/frontend-tools.contract.json` is
generated (`WRITE_FRONTEND_CONTRACT=1 pytest …/test_frontend_tools_contract.py`) but carries **no
`GENERATED` header marker** — invisible to the obvious grep, and therefore hand-editable without
anyone noticing. The manifest must carry the marker `tool-liveness.json` already models.

---

### 🟠 F10 — A declaration that regresses after admission cannot be un-admitted

§5 makes telemetry mandatory and non-skippable — genuinely good, and it would *see* a loud regression.
But §0.1 states the admitted set changes **only by deploy**, and §6 defines no exit. So there is no
threshold, no owner, no automatic withdrawal, and no *quarantine* state between admitted and absent.

Three things make this worse than it sounds:

1. **The dangerous regressions are quiet.** DESIGN-HYPOTHESIS §4.1 is explicit: *"both the proposal and
   the cheap rival convert loud failures into quiet ones… any acceptance criterion built on an error
   rate will improve while correctness degrades."* §5's wrong-object counter is the only detector, and
   the design gives it **no threshold and no consumer**.
2. **Withdrawing a declaration re-triggers F1 and F3** — a downstream consumer bound to its `emits`
   becomes unresolvable (M5), so a single withdrawal cascades through the dependency closure nobody
   computes.
3. **The regression also lands on the control group** (F4), so the A/B drifts in the same direction and
   the comparison hides it.

---

### 🟡 F11 — Admitted then unused: no de-admission, and the noise the membrane exists to prevent re-accumulates

The empty-runtime premise is *"only a surface with no noise can prove the new architecture works."* An
admitted-but-unused declaration **is** noise. §6 has no usage floor, no review interval, no sunset.

The repo's measured trajectory says this is the default outcome, not an edge case: **192/315 never
called, 225/315 never succeeded, 14 tools at ≥5 calls with 0 successes** *(RT4 §0)*. Nothing in the
old runtime ever retired any of them — *"exactly one [mechanism] was ever retired"* (AUDIT §28). SPEC
R9.6's usage counters (the retire criterion) are **specified and not built**.

**Tension the design should resolve explicitly rather than leave implicit:** §0.3's *"defer, never
delete"* argues *against* de-admission, and it is right for the model-facing action space. But
de-admission is a **framework-side, deploy-time** act, invisible to the model — it is the §0.1
`admitted` set, not the `advertised` set. The two are not in conflict, and the design should say so
and then define the criterion. As written it says neither.

---

### 🟡 F12 — A rollback un-admits a declaration that an in-flight plan still references

§0.4 makes the plan durable data; §0.5 says *"No plan may terminate except by satisfying its `done_when`
or by reaching a human. `interrupted` is a defect, not an outcome."* The suspend/resume machinery is
real (`suspended_runs` + `finish_reason='awaiting_input'`, §0.5).

A deploy that admits declaration N is rolled back. A suspended plan resumes with a step naming N. M5
makes the reference unresolvable — so the plan can satisfy neither `done_when` nor reach a human by
any defined path, which §0.5 calls a defect.

Nothing defines: whether a plan pins the manifest version it was authored against; whether resume
re-validates its step references; or what plan-level class (§0.5: step-local / binding-invalid /
plan-invalid / needs-human) an un-admission maps to. `plan-invalid → replan` is the plausible answer
and it is not stated.

---

### 🟡 F13 — A declaration whose provider is unreachable: admitted, but not servable

The manifest is static and generated at build time; providers are ten federated services with a
cached catalog, a refresh timer, degradation gating, and a `/health/federation` 503 *(RT4 §23)*.

Is an admitted declaration whose provider is down **withheld** (§5.2, with stage + reason) or a
manifest error? §5.2 requires `{tool, stage, reason}` for every withholding and states that *"a
withholding that does not register is a defect"* — but **ARCHITECTURE.md never enumerates the reason
set**. SPEC R4 does (`artifact` / `policy` / `runtime`, closed enums per layer, *"a reason may not
cross layers"*), and "provider unreachable" fits none of its three layers cleanly. Carry R4's enum
into ARCHITECTURE and add the case, or the first real outage produces an unregistered withholding —
the defect §5 names.

---

### 🟡 F14 — Nothing prevents a name collision across the membrane

M2 guarantees the new assembler never *reads* the old catalog. It says nothing about **names**. Both
runtimes route by name, and ai-gateway routes by **hardcoded prefix maps** (`DEFAULT_PREFIX_MAP`,
`EXTRA_PREFIX_MAP`, `config.ts:90-135`) *(RT4 §22)*. A new-runtime declaration reusing a live tool's
name gives one name two behaviours, resolved differently per consumer — and per F4 they share a
provider, so which one answers depends on the prefix map, not on the manifest.

Under F4's fork option this becomes routine, not exotic: every forked declaration needs a name that is
new to `TOOL_POLICY` (F7), new to the prefix maps, new to the 5 i18n label keys × 18 locales, and new
to the 16 studio effect RegExps — *"`matchEffectHandlers` filters; an unmatched pattern raises
nothing. The GUI simply stops refreshing after agent writes, with no error anywhere"* *(RT4 §11)*.
**Naming is an admission concern here and the design does not treat it as one.**

---

### 🟡 F15 — "Besides the runtime's own primitives" is an un-admitted always-present set

§6.2's solo run permits *"the runtime's own primitives"* on the surface and never enumerates them.
Today that set is load-bearing and model-facing: `tool_list`, `tool_load`, `find_tools` are
**always-allowed, scope-independent** on the public edge (`tool-policy.ts:72-76`), and the repo's own
recorded lesson is that discovery via `tool_list → tool_load` is what makes a weak model work at all.

If those primitives are on the solo surface, they are **not empty, not contract-checked, and not
admitted** — a standing exemption inside the mechanism whose entire claim is *"only a tool built to
the new architecture can load into it."* If they are *not* on the surface, brick 2's *"the surface is
empty and the agent says so honestly"* has no tool through which to say it.

---

## 6 · What admission must plug into — the existing gate estate

Not findings, but constraints M1–M5 inherit the day they are written, and two ready-made repairs.

| fact | consequence for P3 |
|---|---|
| **`gates.yml` auto-discovers by filename predicate** — `gate-wiring-gate.py --run-all` executes every `scripts/*-gate.*` / `*-lint.*` | a new `scripts/admission-gate.py` **runs in CI the day it lands**, and reds `gate-wiring-gate` until it is wired or `EXEMPT` with a reason. Good news: M1/M2/M5 get enforcement for free |
| **`gate-teeth-gate.py`** requires every CI gate to contain a *reachable non-zero exit*, ratcheted | M1's *"row count == admitted count"* must be red-able, and F8 says it currently cannot be — a tautology has no reachable red |
| **`enforcement-claims-gate.py`** (the estate's strongest, fail-closed) requires every row in the machine-contract table of `docs/standards/README.md` to exist **and be read by a non-test source** | `contracts/agent-runtime-manifest.json` **must be registered there** or it is ungoverned; once registered it fails closed if nothing reads it — which is exactly the M2 property, obtained from an existing gate |
| **`tier-tag-gate.py:170-174` is the only script in the estate with a non-vacuity guard** — *"the parser matched nothing, which means it is broken, not that the tree is clean. Failing rather than passing vacuously"* | **copy this into every M1–M5 gate.** Every other catalog script in the estate passes vacuously on empty input, and that is how 223-vs-315 survived |
| **`deprecated-tool-scan.py` fails open three ways**: rails file missing → silently unscanned; a name in *no* catalog is dropped (`if tok in legacy`) so a **phantom tool is invisible**; glob-derived catalog with no non-vacuity guard | this is the script whose job the manifest takes over. Its three fail-opens and its `DEAD_TO_DEAD_BASELINE = 9` ratchet all disappear with it — a real simplification P3 can claim |
| **`liveness.go:66-84` is *degrade-safe by design*** — unreadable manifest ⇒ gate goes **INERT** and logs; `toolBlocked` blocks only explicit `executes:false`, and absent-from-manifest is *"unknown, not broken"* → warning only | **the membrane must invert exactly this.** M1's whole claim is that absent = inadmissible. The repo's existing manifest gate says absent = fine. Whoever writes M1 must consciously reject the pattern sitting next to it, and the repo's own lesson `degrade-safe guard must surface "unverified"` applies |
| the rails fail-open is **four layers**, only one in `scripts/` — the scan (above), `liveness.go` (inert/warn-only), `workflows.go:139-190` `validateWorkflow` (bypassed by the raw `INSERT` seeds at `migrate.go:497-782`), and `migrate_lint_test.go` (checks apostrophes, `done_when` grammar, `DO UPDATE` — **never `tool`, `gate`, `repeat`, or step `id`**) | M5 replaces all four. Worth stating in ARCHITECTURE.md, because *"a gate that fails open"* undersells it: **there is no layer that checks a workflow's tool names at all** |
| **there is no tool/skill/workflow catalog under `contracts/` today** — `tool-liveness.json` is eval-derived (`executes`/`proven` booleans), with no group, service, tier, or scope column, and blind to consumer-local tools | M1 is net-new, not a refactor. §3's throughput budget must include *building the generator*, and §7's *"snapshot `tools/list` into `contracts/`"* prerequisite is the first half of it |

---

## 7 · The three that should change the design, not just be logged

1. **F3 + F6** — the admission *unit* is wrong. §6 admits one tool; §0.2 and M1 define the unit as a
   declaration, and the design's most important test (Brick 4) needs a **set**. Fixing the unit fixes
   both, and it is a small edit to §6 rather than a new mechanism.
2. **F4** — §7's control group is the stated justification for keeping the old runtime, and admission
   contaminates it by construction. This needs a decision (fork / negotiate / accept), not a gate.
3. **F2 + §3** — §6's learning loop and §6.3's evidence bar are individually correct and jointly
   unaffordable. **13 admissions/week with ≥377 synthetic solo turns/week against a product that
   generates 414 tool calls/week in total** is the number §0.3 asked for, and it says the membrane
   becomes the ceiling long before the catalog clears. A stated minimum bound, a contract-version
   stamp, and a per-phase rate *target* (not just a report) are the cheapest repairs.

**What is not in doubt:** M2 is correct and should not be weakened by anything above. Every finding
here is about what happens *after* a declaration reaches the manifest — which is precisely the half
§6 leaves as one paragraph.
