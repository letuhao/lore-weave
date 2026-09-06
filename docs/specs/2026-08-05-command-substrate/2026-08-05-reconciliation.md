# Reconciliation — the 2026-08-05 round against the 2026-08-02 rounds

> # ⛔ CLOSED 2026-08-06 — FOLDED INTO THE 2026-08-02 ROUND
>
> Every surviving item now has an **08-02 id** and the id is where the work continues:
> `CMD-11` the offer registry · `CMD-12` the keyed-MAC `offer_id` · `CMD-13` horizontal
> composition · `CMD-10` absorbed the N+1 test · `O-CI-23`/`O-CI-24`/`O-CI-25` carry the three
> questions the conflict-resolution proposal left open. See
> [`2026-08-05-reconciliation.md`](2026-08-05-reconciliation.md) §8b for the item-by-item mapping.
>
> **This folder is HISTORY. Do not build from it, do not cite it as current, and do not edit it to
> keep it alive** — an open question living only here is how it stops being asked.

**Status:** the adjudication the quarantine demanded. Read this before any other file
in this folder.

---

## §1 · The finding that reframes everything

`docs/plans/2026-08-02-command-interaction-RUN-STATE.md:85`:

> **`CMD-1`..`CMD-6`** — **NOT sealed. Sealing deferred pending prior art** — the PO
> declined to seal on the argument as written and **directed a round of prior art**.

**The 2026-08-05 round is, accidentally, the prior-art round the PO asked for —
performed without reading the round that asked for it.**

That is not an excuse; it is the correct diagnosis, and it changes what to do with
this folder. The work is not worthless and it is not a replacement. It is a
directed follow-up that duplicated most of its own predecessor because Phase 0
question 1 was answered with a `grep` over `crates/` and `services/`.

---

## §2 · What 08-05 re-invented — and the 08-02 name that wins

Everything in this column already existed, three days earlier, usually better argued.
**The 08-02 name is authoritative.**

| 08-05 called it | 08-02 already had | verdict |
|---|---|---|
| `CMD-D1` — the payload is DATA | **`CMD-1`** — *"a verb is a declared row with an ordinal… `CommandKind`, `InteractionKind` and `CombatPayload` are the same rot at three levels, exactly as `Actor.hp` / `VitalKind` / `StatSlot::MaxHp` were"* | **duplicate, and theirs is stronger** — same `D-3` analogy, reached first, and **not sealed**. `CMD-D1`'s "seal" is void: it sealed a decision the PO had already declined, under a colliding id |
| the Offer layer (§1, §3) | **`from: Offered \| Any`** on `RoleSpec` (§4.1), explicitly *"generalises `THR-A4`, which is today implemented inside the `strike` arm and nowhere else"* | **duplicate** |
| provider ≠ subject (§2) | **`RoleSpec.role = Agent \| Instrument \| DirectTarget \| IndirectTarget`** | **duplicate, and theirs is finer** — my "provider" is their `Instrument`, and they also separate direct from indirect target |
| §10 the pipeline | **§5's nine stages**, sourced to Inform 7's shared-vs-per-action rulebook split, with a per-stage shipped/half/absent status column | **duplicate, and theirs is far better** — mine is a diagram, theirs is an audit |
| §7 declared preconditions, 5 kinds | **`RequirementRow`**, 7 engine-closed kinds, each *"a bit test or a comparison against state `ActorQuantities` already holds"* | **duplicate, and theirs is implementable** — mine invented `LinkExists`/`Adjacent`/`ValueAtLeast` with no substrate |
| §7 declared effects | **`EffectRow`** over 7 closed primitives, with the closure rule: *"a primitive exists **iff the actor substrate already built the door** it goes through"* | **duplicate, and theirs closes the set non-arbitrarily** — mine said "the engine owns the alphabet", which is a restatement, not a test |
| extensibility §3, the god class | **`CMD-6`** — *"binding a declared name to an engine operation must be TABLE-DRIVEN, not a `match` arm"*, with §1.1 showing `contains("cast") → true` while `validate(…"cast") → Err(UnknownTool)` — **two answers to one question, one function apart** | **duplicate, and theirs has the receipt** |
| §11 research (GAS · Skyrim · RTS · WoW) | **§3's six systems** — The Sims · GAS · Inform 7 · Caves of Qud · Evennia · lockstep — with *"none was consulted before the measurement, so agreement is evidence rather than anchoring"* | **overlapping, and theirs is methodologically cleaner.** See §4 |
| the N+1 agent's ordinal-ceiling finding | **§4.2 / `C-3`** — *"`MAX_DECLARED_QUANTITIES = 32` is nowhere near enough for verbs, and raising it is `O-97`'s engine capability width problem"* | **already known, already priced** |

---

## §3 · What 08-02 has that 08-05 MISSED — including the thing the red team caught me on

These are not duplicates in the other direction. They are gaps in the 08-05 round.

1. **`submitter_class: Player | Controller | Engine`**, generalised from `EndTurn`'s
   own comment. The grounding lens found that extensibility §7.2 attributes
   `EndTurn`'s protection to `sim-core`'s ingress separation, which is **wrong** —
   the protection is `Vocabulary::validate`'s closed `match`, the very closure
   `CMD-D1` dissolves. **08-02 had already turned that hand-written property into a
   column.** They solved the problem I mis-described.
2. **Refusal is a committed fact** carrying `stage` + `reason` ordinal (`CMD-5`).
   08-05 has nothing on refusal at all.
3. **Presentation is a separate channel** — a cue ordinal, no prose, and
   `renderEvent`'s per-verb `switch` named as shipped-wrong (`CMD-4`). Nothing in
   08-05.
4. **`origin: Recomputable | Oracle` per EFFECT ROW**, with the argument for why it
   cannot live on the verb (*"`speak` emits an Oracle narration AND a deterministic
   opinion delta"*). This is a partial answer to the determinism lens's interpreter
   worry, and 08-05 never reached the question.
5. **A rot ledger, `C-1`..`C-12`, line-accurate against a named base commit.**
6. **`A-1`..`A-7` — "where this design is most likely wrong", written by the author
   before the red team arrived**, including `A-6`: *"stage 4 commits cost before
   stage 5 adjudicates… **this is the sharpest edge and the author knows it**."*
7. **Its own vacuity finding, self-reported:** *"🔴 §2's classification test is
   WITHDRAWN — it cannot fail."*

---

## §4 · The prior art: what the directed round actually added

Four of 08-05's systems overlap 08-02's six. Honest accounting:

**Genuinely new, and worth keeping:**
- **Skyrim ESM/ESP** — the *pre-compose vs load-time composition* argument, and the
  SaaS reason for refusing load-time composition. 08-02 has Caves of Qud's
  `Load="Merge"` and Evennia's cmdset priority merge, but neither carries the
  *"a build can fail where a launch cannot"* argument.
- **GAS client-prediction / server re-run** — confirms offer-as-hint. 08-02 cites
  GAS for cost-as-effect and tag requirements, not for the prediction model.

**Duplicated:** lockstep (08-02 §3, same conclusion, better phrased) · GAS's
tag-set requirements (08-02 §7: *"two systems, no contact, one answer"*).

**Overstated, per the grounding lens:** the WoW claim rests on a third-party
emulator guide and is asserted as shipped Blizzard architecture.

**And two systems 08-02 consulted that 08-05 never did — both answering questions
08-05 left open:**
- **Inform 7** — the shared-vs-per-action rulebook split *is* the pipeline design.
- **Caves of Qud / Evennia** — merge-not-replace and layered command availability,
  i.e. the composition question `CMD-D2` treats as newly opened.

---

## §5 · What 08-05 genuinely adds — the short list

Stripped of duplicates, this is what survives and should be folded into the 08-02
frame under 08-02's ids:

1. **The offer REGISTRY.** 08-02 has `from: Offered` as a *validation flag* at
   pipeline stage 2 and never says what produces offers. `offers_for(subject, tick)`
   is a real gap-filler.
2. **`offer-entitlement` and the keyed-MAC `offer_id`** — and these attack a claim
   08-02 makes. See §6.
3. **The N+1 test** as an explicit, mechanical criterion.
4. **The pre-compose ⇒ a build may FAIL argument.**
5. **The red team itself** — four lenses, findings grounded to file:line, several of
   which land on 08-02 and on shipped code rather than on 08-05.

---

## §6 · Where the two rounds CONFLICT — and who wins

| conflict | 08-02 | 08-05 / red team | verdict |
|---|---|---|---|
| is the confused-deputy guard correct today? | §5 stage 0: *"✅ shipped — and the confused-deputy guard is already correct"* | the security lens: `actorForUser` returns `LW_CHANNEL_DEFAULT_ACTOR ?? '1'` for any authenticated user absent from the env map, so **two users are legitimately bound to one subject** | **red team wins**, with file:line. 08-02's ✅ on stage 0 must be downgraded |
| does `THR-A4` guarantee the engine offered the target? | §4.1 treats it as a real guarantee, implemented for `strike` | the grounding lens: `candidates` is a **wire field the producer supplies**, and `admit_signed` holds no island handle, so it cannot re-derive | **red team wins.** THR-A4 constrains the model relative to its driver, not the driver relative to the engine — which makes the offer registry *more* necessary, not less |
| composition of two declarations | Qud/Evennia **merge**, priority-ordered | `CMD-D2`: collision **fails the build**; amendments add only | **unresolved — needs the PO.** Two coherent answers. Merge is proven in two shipped systems; build-failure is only available to us because we pre-compose |
| does the holder relation mean ownership? | **`ITD-1`: OWNERSHIP and LOCATION are two different questions** — a borrowed sword is `HeldBy(disciple)` and owned by the master; **theft is exactly the gap between them** | `LinkExists` — *"the subject holds the provider"* | **`ITD-1` wins outright.** `LinkExists` silently collapses the distinction the item round exists to make |

---

## §7 · The 🔴 BLOCKER is WITHDRAWN

08-05 declared: *"no holder graph exists… today there is no outside."*

The measurement was right and the conclusion was wrong. `2026-08-02-item-data-structure.md`
(611 lines) + `2026-08-02-item-dataflow.md` (1 318) are *"the substrate under
**ownership, inventory, equipment and transfer**"* — with `§3 Who may HOLD`,
`§5 Transfer — the single-place rule IS the anti-duplication mechanism`,
`§7.5 The operation set is CLOSED`, decisions `ITD-1`..`ITD-15`, a rot ledger, and
**two recorded PO corrections**.

Per `CLAUDE.md`, designed-and-unbuilt is **"unbuilt work to implement"**, not
blocked. Calling it a blocker was the anti-laziness rule's exact failure mode:
*"saying 'blocked' when you mean 'I'd have to build it'."*

---

## §8b · ✅ DISCHARGED 2026-08-06 — the fold happened, and where each item went

This folder is now **history**. Everything below that survived has an 08-02 id, and the id is where
the work continues; nothing here is authoritative and nothing here should be edited to keep it alive.

| §5 survivor | landed as |
|---|---|
| the offer **registry**, `offers_for(subject, tick)`, and where it runs | **`CMD-11`** (RUN-STATE §4e) — carrying the red team's finding that `THR-A4` constrains the model relative to its **driver**, not the driver relative to the engine, which makes the registry necessary rather than decorative |
| `offer-entitlement` + the keyed-MAC `offer_id` | **`CMD-12`** — with the same-tick leak stated as a limit, and with the security lens's `actorForUser` finding attached, because a MAC over a subject the caller can already be is a lock on the wrong door |
| the pre-compose ⇒ **a build may FAIL** argument | **`CMD-13` part ④**. It is the argument that makes the whole mechanism affordable, and it is the one thing 08-02's Qud/Evennia prior art did not carry |
| the **N+1 test** as a mechanical criterion | **`CMD-10`** absorbed it: V1–V4 are the N+1 test made answerable per-concern, and V4 is the question N+1 could not ask |
| the **red team** | re-homed. Its findings about **shipped code and the 08-02 design** outlive this folder — four of them are now `D-REPLAY-PIN-REFUSAL-UNDEFINED`, `D-RNG-COORDS-SNAPSHOT-ONLY`, `D-NO-INPUT-LOG`, and a fixed `FATAL-1` |
| the conflict-resolution proposal (deliberately unnumbered) | **`CMD-13`**, with its three open questions promoted to **`O-CI-23`** (is the strategy set complete), **`O-CI-24`** (where a resolution is authored), **`O-CI-25`** (does `strict` earn a member) — because an open question living only in a quarantined folder's prose is how it stops being asked |

**`CMD-D1`..`CMD-D7` remain RETIRED.** They were never re-used: the fold deliberately allocated
`CMD-10`..`CMD-13` in the live sequence rather than rehabilitating a colliding prefix.

## §8 · What to do

1. **`CMD-D1`..`CMD-D7` are RETIRED as ids.** They collide with live `CMD-1`..`CMD-9`
   on the same subject. Anything that survives re-enters under an 08-02 id or a new
   non-colliding prefix.
2. **`CMD-D1`'s seal is VOID.** It sealed what `CMD-1` proposes, which the PO had
   explicitly declined to seal pending prior art.
3. **Fold §5's five survivors into the 08-02 round** as the prior-art return it
   turns out to be.
4. **Re-home the red-team findings.** Most do not belong to 08-05 at all: the
   `externals()` whitelist, the default-`PASS` precondition arm, `LAW_VERSION`'s
   hand-bump against an interpreter, `tick`-as-input-counter, and the
   `actorForUser` fallback are findings about **shipped code and the 08-02 design**,
   and they outlive this folder.
5. **The one thing 08-05 got right that nothing else covers:** `CMD-1` cannot be
   sealed without answering *what pins the interpreter's behaviour into the digest*.
   `ruleset.rs` already records that exact failure once (`QTY-D13`), and a
   hand-bumped `LAW_VERSION` is the only thing standing there.
