# COMB_006 — PvP & Stakes

> **Conversational name:** "PvP" (PVP). The consent model that makes two PCs attackable, the stakes they
> fight under, and the social consequence of winning. Closes **COMB-Q3**, the last open question in the
> combat family, and discharges **PC-D2** — locked *"PvP enabled within a session"* on **2026-04-23** with
> its consent model deferred to DF4/DF5 and never built.
>
> **Category:** COMB — Combat (COMB_006)
> **Status:** **DRAFT 2026-07-26**. Delivery target **V1+** (user direction 2026-07-26, pulling forward
> from DF5-D3's V2 deferral — the design lands now, while the combat family is fresh, because V1 choices
> were already at risk of silently foreclosing it; see §12).
> **PVP-Q1..Q10 LOCKED** in this pass; `PVP-A1..A8` axioms codified.
> **Stable IDs in this file:** `PVP-A*` axioms · `PVP-Q*` decisions · `PVP-D*` deferrals · `PVP-V*`
> validators · `AC-PVP-*` acceptance criteria. Owns the `pvp.*` reject namespace.
> **Builds on:** [COMB_001](COMB_001_combat_foundation.md) §6 encounter SM + Q3 mortality + Q4 disparity
> cap · [COMB_004](COMB_004_loot_and_spoils.md) §16 **the Binding Contest** (the item-stakes half) ·
> [COMB_005](COMB_005_encounter_spawning.md) §5 engagement predicate + §6.1 formation ·
> [WA_006](../02_world_authoring/WA_006_mortality.md) `MortalityConfig` · [WA_001](../02_world_authoring/WA_001_lex.md)
> Lex axioms · [PF_001](../00_place/) `combat_safety` · [REP_001](../00_reputation/) notoriety ·
> [FAC_001](../00_faction/) `RelationStance` · [TDIL_001](../17_time_dilation/) A1/A6 turn economics ·
> [DF05_001](../DF/DF05_session_group_chat/) session scope · [PCS_001](../06_pc_systems/) PC substrate.
> **Where this doc lives, and why here:** [`02_world_authoring/_index.md`](../02_world_authoring/_index.md)
> reserved `WA_NNN_pvp_consent` for PC-D2 and wrote that *"the others have stronger affinity to their
> consumer (**PvP→combat**) — when those consumer features open, their author may choose to put the
> override in their own folder."* Combat is now open; the condition fired. **No WA_NNN is needed.**

---

## §1 — Purpose & scope

### What was actually open

COMB-Q3 was mis-stated as *"PvP is missing"*. It was not a missing decision — it was a **built decision
with no mechanism**:

| Already locked | Where | Since |
|---|---|---|
| PvP is **enabled**, consent-gated | `PC-D2` in [`locked_decisions.md`](../../decisions/locked_decisions.md) | 2026-04-23 |
| Consent model deferred to DF4 World Rules + DF5 Session | PC-D2's own note | 2026-04-23 |
| DF5 deferred it again → V2 | `DF5-D3` / `DF5-40` | 2026-04-27 |
| V1 behaviour is *"enabled within session"*, **hardcoded** | `02_world_authoring/_index.md` | — |
| PvP-ranked titles wait on it | `TIT_001` survey | 2026-04-27 |
| Newbie-gank prevention is **already solved** economically | `TDIL-A1` / `TDIL-A6` | 2026-04-27 |

So this doc supplies the mechanism, and corrects one thing: *"within a session"* was written under the
**text/chat medium** (2026-04-23) and predates the 2026-06-20 medium correction. The
[blast-radius audit](../../10_medium_blast_radius_audit.md) swept social/meta for stale text assumptions
but could not sweep PvP, because PvP had no design to sweep. §4 reopens exactly that phrase and nothing
else.

### V1+ minimum scope

- **Two consent channels** (§3–§4): `Duel` (explicit mutual accept, with declared stakes) and
  `ContestedZone` (a PF_001 safety band where entering *is* consent). `FactionWar` is structurally
  unavailable until DIPL_001 — see PVP-Q3.
- **A reality master gate**, default **Disabled** (§2, PVP-A2).
- **Full WA_006 mortality applies** (user direction; PVP-A4) — with the **Binding Contest**
  ([COMB_004 §16](COMB_004_loot_and_spoils.md)) as the mechanism that makes permadeath survivable rather
  than merely brutal.
- **Disparity-cap inversion** (§6) — the single most important rule here: a consensual duel must
  *bypass* the protection that would otherwise make it unplayable, and the same axis read backwards is
  what licenses binding severance.
- **REP_001 notoriety** as the social consequence of a kill (§7).
- **9 V1 rule_ids** in the `pvp.*` namespace + **7 validators** PVP-V1..V7 + **AC-PVP-1..14**.

### V1+ NOT shipping

| Feature | Defer to | Why |
|---|---|---|
| `FactionWar` consent channel | DIPL_001 (PVP-D1) | FAC_001 `RelationStance` is a closed 3-variant enum **static at canonical seed** (Q5 LOCKED) — there is no `AtWar` state to read. Shipping it needs a dynamic diplomacy layer, not a PvP change |
| Ranked/rated PvP, ladders, matchmaking | V2 (PVP-D2) | needs a rating system and queueing; `TIT_001` already reserves PvP-ranked titles for "if PvP ships" |
| Territory capture / siege | V3 (PVP-D3) | COMB_001 §10 already defers multi-cell siege; territory needs an ownership model PLT_001 only partly covers |
| Bounty / contract-kill systems | V2 (PVP-D4) | needs the economy module (AUD-F11, accepted V1 cut) |
| Team/arena instanced modes | V2 (PVP-D5) | duels are 1v1 V1+; party-vs-party reopens `sides` formation (COMB_005 §6.1) |
| Non-lethal subdual / capture-and-ransom | V1+30d (PVP-D6) | COMB_001 §5 already defers capture; ransom needs economy |
| Cross-reality PvP | **never** (PVP-D7) | peer-reality isolation is a platform invariant (RTM-A7); PvP cannot be the thing that breaches it |
| Duel spectating / wagering | V2 (PVP-D8) | pure surface; no mechanism blocked by its absence |

---

## §2 — Axioms

- **PVP-A1 (Consent is a channel, never a default).** Two PCs are attackable **only** when a declared
  channel says so (§3). There is no ambient "PvP is on" state inside an enabled reality. The engine
  evaluates channel eligibility as a pure predicate, exactly as COMB_005 §5 evaluates NPC aggro.
- **PVP-A2 (The master gate defaults to Disabled).** `RealityManifest.pvp_policy` is `Option<PvpPolicy>`;
  `None` ⇒ PvP is **unreachable**, and every PC-on-PC `Strike` rejects as it does today. Rationale, stated
  because it is the single most consequential default in this doc: **WA_006's own default is
  `Permadeath`** (PC-B1). A reality that opts into neither config would otherwise let a stranger
  permanently delete a character, with no author having chosen that. Two harsh defaults must not compose
  silently — so one of them is opt-in.
- **PVP-A3 (Engine decides eligibility; the LLM never starts a PvP fight).** Extends COMB-A1 and SPN-A5.
  An LlmDriver-controlled actor can never be a PvP *initiator* (it is not a PC), and no narration layer
  can conjure a duel. Consent is a player act or a spatial fact — never a generated one.
- **PVP-A4 (PvP defeat is death, on the same terms as any other death).** Full WA_006 `MortalityConfig`
  applies, including `Permadeath` where the reality declares it, and per-actor `mortality_role`
  (COMB_001 Q3) still overrides. **PvP is not a special death.** *(User direction 2026-07-26, choosing
  consistency over a softened PvP-only path. What makes this survivable is not a weaker death — it is the
  Binding Contest, COMB_004 §16: what you lose is contestable, degradable and reclaimable, rather than
  simply gone.)*
- **PVP-A5 (Consent buys the right to be hurt, and nothing else).** Entering a channel waives the
  disparity cap *between the consenting parties only* (§6). It does not waive the Lex safe-zone axiom for
  bystanders, does not permit targeting non-consenting actors, and does not survive leaving the channel.
- **PVP-A6 (A kill is a social act).** Every PvP kill emits REP_001 notoriety scaled by the channel and by
  the victim's standing (§7). A world with FAC_001 / REP_001 / TIT_001 / PLT_001 already built has the
  machinery to make killing *mean* something; PvP that produces no social consequence wastes it.
- **PVP-A7 (Declarations are System-tier).** `pvp_policy`, contested-zone bands and duel rules live in the
  RealityManifest, author/admin-write only, edited via an audited `Forge:EditPvpPolicy`. No player action
  changes who may be attacked where — that would let one player open another's sanctuary.
- **PVP-A8 (No new aggregate).** A pending duel challenge is ephemeral (§3.2); an active duel **is** a
  `combat_session` (COMB_001 §2); contested status is a PF_001 place property. The family's
  zero-new-aggregate property survives PvP.

---

## §3 — Channel 1: the Duel (PVP-Q1 LOCKED)

### §3.1 Stakes are declared at challenge time

A duel is **mutual, explicit and staked**. The challenger names the stakes; accepting agrees to them.

```rust
pub enum DuelStakes {
    /// 切磋 — a spar. Defeat is KO only; WA_006 is never reached; no item consequence.
    Spar,
    /// 生死战 — a life-and-death duel. Full WA_006 applies (PVP-A4); the Binding Contest is eligible.
    LifeAndDeath,
}
```

Both stake levels ship in V1+, and the pair is the point. `Spar` gives two players a way to test
themselves with **zero** risk — the thing a duel-only-if-lethal design cannot express. `LifeAndDeath` is
the genre's actual centrepiece (a wuxia/tu-tiên world without 生死战 is missing something its own fiction
assumes) and it is *fully consented on both sides*, which is what makes permadeath defensible here in a
way an ambush never would be.

### §3.2 The challenge handshake

```
Challenger issues Duel:Challenge { target, stakes }            → ephemeral DuelOffer, TTL 3 fiction-minutes
Target responds  Duel:Accept | Duel:Decline                    → decline is silent to third parties
On Accept:
   1. re-validate BOTH sides' eligibility (§5) — consent can go stale in 3 minutes
   2. form an instanced encounter (COMB_005 §6 formation; RTM-Q4 dedicated scene)
   3. CombatSessionBorn with pvp_context = Duel { stakes }
```

- **The offer is ephemeral** — a `DuelOffer` in the cell's transient state, never an aggregate (PVP-A8).
  Expiry is silent; a lapsed challenge is not a rejection.
- **Re-validation on accept is load-bearing.** Between challenge and accept a player can walk into a
  sanctuary, be KO'd, join another encounter, or have the reality's policy edited. Accepting a stale offer
  must not create an encounter that the channel predicate would now refuse. `PVP-V3`.
- **Declining is private.** A public decline is a social-pressure vector — it makes refusing a fight
  costly, which converts "consent" into coercion. Only the challenger learns of a decline.
- **A duel is instanced**, so bystanders cannot be caught in it and it cannot be used to drag a third
  party into combat (PVP-A5).

---

## §4 — Channel 2: the Contested Zone (PVP-Q2 LOCKED · resolves the medium question)

### §4.1 Consent is spatial

PF_001's `CombatSafetyLevel` gains a band. Entering a `Contested` place **is** the consent — the same
model every open-world MMO converged on, and the one *"within a session"* could not express once the
medium became a shared traversable world (§1).

| `CombatSafetyLevel` | PvP | Notes |
|---|---|---|
| `Sanctuary` | ✗ never | COMB_005 SPN-V4 already forbids hostile spawns here too |
| `Newbie` | ✗ never | TDIL-A1/A6 turn economics *plus* a hard prohibition |
| `Normal` | ✗ (duels only) | the default world; a duel may still be agreed anywhere non-sanctuary |
| **`Contested`** | ✓ **open** | full stakes (PVP-A4), Binding Contest eligible, notoriety applies |
| `Perilous` | ✓ open | already the highest PvE danger band; PvP composes |

- **The boundary is legible or it is a trap.** A player must be able to know, before crossing, that they
  are entering a place where other players may kill them. This doc requires the *data* (the band is on the
  place, readable at any Examine depth and on the map layer) and leaves the *presentation* to the
  client-build track — but a `Contested` band that is not surfaced is a **defect**, not a UI gap
  (`PVP-V6`).
- **Crossing out is immediate.** There is no "PvP flag timer" that follows a player into safety. Rationale:
  a timer is a second, invisible state that contradicts the visible one — the place is the truth. The
  cost is that a losing player can flee to a `Normal` tile; that is a *feature* (an escape is a real
  tactical option, and COMB_001 `Flee` already exists), not an exploit.
- **An active encounter is not cancelled by crossing out.** COMB_001's encounter SM owns resolution;
  fleeing the zone means fleeing the *encounter*, on the existing `Flee` terms. Otherwise stepping over a
  line mid-swing would void a fight, which is the exploit the timer was invented to stop — and this
  formulation avoids needing the timer at all.

### §4.2 What this reopens, precisely

**PC-D2's *"within a session"* is amended, not overturned.** The decision's substance — *PvP is enabled and
consent-gated* — stands untouched. Only its scoping phrase is medium-stale: under a chat medium, "a
session" was the only place two PCs could co-exist, so "within a session" *was* the consent. Under the
rendered medium two PCs co-exist by standing in the same cell, and the phrase would either forbid PvP
entirely (no sessions in open world) or permit it everywhere (the world is one session). Neither is what
was meant. **`Duel` preserves the original intent** (an explicit, bounded, mutually-entered context —
exactly what a session was) and **`ContestedZone` supplies what the new medium made possible.**
Recorded as an `ILR`-class medium reconciliation, and cross-referenced from PC-D2.

---

## §5 — The eligibility predicate (engine-owned, PVP-A3)

```pseudo
fn pvp_eligible(attacker: Pc, defender: Pc, place) -> bool:
       reality.pvp_policy.is_some()                                  // PVP-A2 master gate
    ∧  attacker.reality == defender.reality                          // RTM-A7; never crosses (PVP-D7)
    ∧  attacker != defender
    ∧  ( in_active_duel(attacker, defender)                          // channel 1 — mutual, staked
       ∨ ( place.combat_safety ∈ {Contested, Perilous}               // channel 2 — spatial
           ∧ reality.pvp_policy.zone_channel_enabled ) )
    ∧ !lex_forbids_pvp(reality, place)                               // WA_001 axiom, still supreme
    ∧ !defender.is_newly_incarnated_grace(reality.pvp_policy)        // §5.1
```

Everything is a pure predicate over engine state — no RNG, no LLM, no seed role. Same discipline as
COMB_005 §5, and it means the PvP surface is **statically analysable**: one function decides it.

### §5.1 Post-incarnation grace

A player who has just died and re-incarnated is, for `grace_fiction_minutes` (default 10), **not a valid
PvP target** — even in a contested zone. Without this, permadeath (PVP-A4) plus a contested zone at a
respawn point is a **spawn-camp that ends characters**, which is the one failure mode this design
absolutely cannot ship with. The grace is *one-sided*: attacking during it forfeits it immediately, so it
protects the vulnerable without becoming a shield to hide behind.

---

## §6 — The disparity-cap inversion (PVP-Q4 LOCKED — the load-bearing rule)

COMB_001 Q4's disparity cap flattens damage (flat 50%/blow) when a strong actor strikes a much weaker one.
It exists to make ganking pointless. Applied naively to PvP it produces **two opposite failures at once**:

| Naive application | Failure |
|---|---|
| Cap applies inside a consented duel | two mismatched friends *cannot* have a real fight; the safety net makes the consented mechanic unusable |
| Cap applies in a contested zone | a strong player is un-killable-by and un-punishing-to the weak; the zone's danger is fictional |

> **PVP-A5 restated as a rule:** inside a channel, **the disparity cap is waived between the consenting
> parties, and only between them.** A bystander in the same cell is still protected. Leaving the channel
> restores it immediately.

**And the same axis read backwards is the licence for binding severance.** COMB_004 §16's *overwhelm*
path — the user's *"still lost … if the enemy have special ability or too strong"* — fires on the very
same power ratio the disparity cap measures, in the opposite direction:

```
ratio = attacker_power / defender_power        (COMB_001 Q4's existing measure, reused verbatim)

ratio ≥ disparity_threshold  ∧  cap_applies   →  DAMAGE IS CAPPED        (Q4: protect the weak)
ratio ≥ overwhelm_threshold  ∧  cap_waived    →  BINDING MAY BE SEVERED  (COMB_004 §16: reward the strong)
```

**These are mutually exclusive by construction**, because `cap_applies` and `cap_waived` are complements.
A place where the weak are protected is a place where bindings cannot be stripped; a channel where the
cap is waived is a place where they can. One number, one comparison, two opposite consequences that can
never both fire — which is why this is a rule rather than two features that must be kept in sync.

---

## §7 — Social consequence (PVP-A6)

| Signal | Effect |
|---|---|
| **REP_001 notoriety** | every kill emits notoriety, scaled by channel (`Spar` = 0 · `LifeAndDeath` = low, it was consented · `ContestedZone` = full) and by the victim's REP standing — killing the notorious is *less* costly, which is how a bounty-hunter identity emerges without a bounty system (PVP-D4) |
| **FAC_001 standing** | a kill across a `Hostile` faction line costs nothing with your own faction and may *raise* it; killing an `Allied`-faction PC is the expensive case |
| **TIT_001** | PvP-ranked titles unblock (their survey deferred them to *"if PvP ships"*) — V2, PVP-D2 |
| **ACT_001 `actor_actor_opinion`** | the victim's NPC allies remember; this is the durable-sentiment layer COMB_003 deliberately refused to duplicate (THR-Q6), now with a genuine writer |
| **WA_002 Heresy** | unaffected — PvP is not a canon violation |

Notoriety is the *only* new consequence this doc introduces, and it introduces no new storage: REP_001
already owns the aggregate and the decay model.

---

## §8 — `RealityManifest` extension

```rust
pub struct PvpPolicy {
    pub duel_channel_enabled: bool,          // default true when a policy exists
    pub zone_channel_enabled: bool,          // default true
    pub allowed_stakes: Vec<DuelStakes>,     // a reality may permit Spar only
    pub grace_fiction_minutes: u16,          // default 10 (§5.1)
    pub overwhelm_threshold_milli: u32,      // §6 / COMB_004 §16; default 3000 (3×)
    pub notoriety_scale: NotorietyScale,     // §7
}
// RealityManifest.pvp_policy: Option<PvpPolicy>   — None ⇒ PvP unreachable (PVP-A2)
```

A reality that wants classic consensual-only PvP sets `zone_channel_enabled: false` and
`allowed_stakes: [Spar]`. A hardcore reality enables both channels and every stake. **A reality that says
nothing gets no PvP at all** — the deliberate asymmetry of PVP-A2.

---

## §9 — Decisions (PVP-Q1..Q10 — LOCKED 2026-07-26)

| # | Question | Resolution & reasoning |
|---|---|---|
| **PVP-Q1** | Duel channel shape? | **Mutual explicit challenge with declared stakes** (§3), `Spar` **and** `LifeAndDeath`. Stakes-at-challenge is what lets one mechanic serve both risk-free sparring and the genre's 生死战 without a second system. Ephemeral offer, re-validated on accept. |
| **PVP-Q2** | Zone channel shape? | **A `Contested` band on PF_001 `combat_safety`** (§4) — entering is consent. No flag timer: the place is the truth, and a timer is an invisible second state that contradicts the visible one. |
| **PVP-Q3** | Faction-war channel? | **Deferred to DIPL_001** (PVP-D1). Not a scoping preference — FAC_001 `RelationStance` is a closed 3-variant enum **static at canonical seed** (Q5 LOCKED). There is no war state to read, and inventing one here would reopen a locked foundation decision from the wrong doc. |
| **PVP-Q4** | Does the COMB_001 Q4 disparity cap apply in PvP? | **Waived between consenting parties, preserved for everyone else** (§6). Applying it would make consensual duels unplayable *and* contested zones fictional — the same rule failing in both directions. The waiver is also what licenses COMB_004 §16's overwhelm path, on the same ratio read backwards. |
| **PVP-Q5** | Defeat consequence? | **Full WA_006, permadeath included** (PVP-A4, user direction). PvP is not a special death. Survivability comes from the **Binding Contest** (COMB_004 §16) — what you lose is degradable, contestable and reclaimable — not from a softer death. |
| **PVP-Q6** | Master gate default? | **Disabled** (PVP-A2). WA_006 already defaults to `Permadeath`; two harsh defaults must not compose without an author choosing. This is the one place this design is deliberately conservative. |
| **PVP-Q7** | Does *"within a session"* (PC-D2) survive the medium correction? | **Amended, not overturned** (§4.2). Its substance (enabled + consent-gated) stands; its scoping phrase was text-medium shorthand for "an explicit bounded mutual context", which `Duel` preserves exactly. `ContestedZone` adds what the rendered medium made possible. |
| **PVP-Q8** | Spawn-camping under permadeath? | **Post-incarnation grace**, 10 fiction-minutes, forfeited by attacking (§5.1). Without it, permadeath + a contested respawn point is a character-ending camp — the one failure mode this design cannot ship with. |
| **PVP-Q9** | Does PvP produce loot? | **No loot-table roll** — COMB_004 §5's refusal stands, and PCs have no `ActorClassRef` table. Item consequence is a **transfer** governed by the Binding Contest (COMB_004 §16), which is a different mechanism with different rules. Generation and transfer must not be conflated. |
| **PVP-Q10** | Where does this live — a `WA_NNN` or COMB? | **COMB_006.** `02_world_authoring/_index.md` reserved `WA_NNN_pvp_consent` *and* named combat as its natural home once combat opened. It has opened. Recorded so the WA reservation can be retired rather than left dangling. |

---

## §10 — Failure-mode UX (`pvp.*` namespace)

| Reject rule | Stage | User-facing message (I18nBundle `default`) | When |
|---|---|---|---|
| `pvp.disabled_in_reality` | 2 validate | "There is no quarrel to be had here." | `pvp_policy` is `None` (PVP-A2) |
| `pvp.no_consent_channel` | 2 validate | "You have no quarrel with them." | neither channel is satisfied (§5) — the default PC-on-PC rejection |
| `pvp.safe_zone_forbidden` | 2 validate | "Not in this place." | `Sanctuary` / `Newbie` / `Normal` zone-channel attempt |
| `pvp.lex_forbids` | 2 validate | (Lex-authored message) | a WA_001 axiom forbids PvP in this reality or place |
| `pvp.grace_active` | 2 validate | "They have only just drawn breath." | defender is inside post-incarnation grace (§5.1) |
| `pvp.duel_offer_expired` | 2 validate | "The challenge has gone stale." | accept after TTL |
| `pvp.duel_eligibility_stale` | 2 validate | "The moment has passed." | re-validation on accept failed (§3.2) |
| `pvp.stakes_not_permitted` | 0 schema / 2 validate | "Such a duel is not fought here." | `stakes` ∉ `allowed_stakes` |
| `pvp.already_engaged` | 2 validate | "They are already fighting." | target is in an active `combat_session` (COMB_005 SPN-V8) |

Per RES_001 §2, every `pvp.*` reject carries `RejectReason.user_message: I18nBundle` with an English
`default` plus a Vietnamese translation from day one.

**Player-visible data contract:** a place's `Contested` band is visible **before** entering (map layer +
Examine at any depth) — PVP-V6. A pending duel offer, its stakes and its remaining TTL are visible to both
parties. Post-incarnation grace is visible on oneself. Notoriety is REP_001's existing surface.

---

## §11 — Validators

| ID | Stage | Check |
|---|---|---|
| **PVP-V1** | 0 schema | `PvpPolicy` sane: `allowed_stakes` non-empty if `duel_channel_enabled`; `overwhelm_threshold_milli > 1000`; at least one channel enabled |
| **PVP-V2** | 0 schema | no place declares `combat_safety: Contested` in a reality with `pvp_policy: None` — a contested zone in a PvP-less world is an authoring error, not a no-op |
| **PVP-V3** | 2 validate | **duel eligibility is re-validated at Accept**, not only at Challenge (§3.2) |
| **PVP-V4** | 2 validate | **the §5 predicate is the only path to a PC-on-PC encounter** — no driver, admin action or ability may create one directly (mirrors COMB_005 SPN-V6) |
| **PVP-V5** | runtime | the disparity-cap waiver applies **only** between consenting parties; a bystander in the same cell retains full Q4 protection (§6) |
| **PVP-V6** | runtime | a `Contested` place's band is present in the client-bound place payload — an unsurfaced contested zone fails, it is not merely undisplayed (§4.1) |
| **PVP-V7** | runtime | post-incarnation grace is enforced at the **predicate**, not at damage application, so no code path can damage a graced actor (§5.1) |

> **PVP-V4, PVP-V5 and PVP-V7 are the non-vacuous set.** PVP-V4 can fail exactly as SPN-V6 can: an admin
> "start duel" tool or a scripted story-duel is the natural shortcut, and it bypasses the master gate, the
> Lex axiom and the grace window at once. PVP-V5 can fail because the waiver is naturally implemented as a
> flag on the *encounter* rather than on the *pair* — and an encounter-scoped flag silently strips
> bystander protection; its bite-test is a third actor in the cell during a duel. PVP-V7 can fail by the
> same misplacement THR-Q7 warns about: guarding grace at damage-time instead of at eligibility leaves it
> one code path from being bypassed, and under permadeath that bug ends characters.

---

## §12 — Why this was designed now rather than at V2

DF5-D3 deferred PvP to V2, and the deferral was reasonable when combat itself did not exist. It stopped
being reasonable the moment the combat family closed, because **V1 decisions were already shaping PvP
without anyone deciding to**:

- COMB_004 §5 wrote *"a defeated PC yields no roll — rolling here would be PvP looting through the side
  door"*. That was the right call, but it was a PvP decision made in a loot doc, by inference.
- COMB_005 §6.1 had to answer *"two mutually-hostile PCs aggroed by one group"* and could only defer it.
- COMB_001 Q4's disparity cap would have made consensual duels unplayable, and nobody would have noticed
  until PvP was built on top of it.

Designing it now costs one document and **changes no V1 code path** (PVP-A2 keeps it unreachable by
default). Deferring it further would have kept accumulating decisions-by-inference in docs that have no
business making them. Delivery still targets V1+; only the *decisions* land now.

---

## §13 — Acceptance criteria (AC-PVP-1..14)

1. **Default reality has no PvP** — `pvp_policy: None`: a PC `Strike` on another PC rejects
   `pvp.disabled_in_reality` in every place, including `Perilous` (PVP-A2).
2. **Spar** — mutual accept, defeat is KO, **WA_006 is never reached**, no item consequence, zero notoriety.
3. **LifeAndDeath** — mutual accept, defeat routes to WA_006 with the reality's `DeathMode` (permadeath if
   so configured), and the Binding Contest is eligible (COMB_004 §16).
4. **Stale accept** — accepting after the challenged party enters a sanctuary rejects
   `pvp.duel_eligibility_stale`; no encounter forms (PVP-V3).
5. **Decline is private** — a third party in the cell observes no event on decline.
6. **Contested zone** — two PCs in a `Contested` place may attack with no handshake; the same two in a
   `Normal` place reject `pvp.safe_zone_forbidden`.
7. **Crossing out** — stepping from `Contested` to `Normal` immediately removes eligibility; an *already
   active* encounter is unaffected and resolves on COMB_001's terms (§4.1).
8. **Disparity waiver is pairwise (bite test)** — during a duel, a bystander struck by a stray effect
   retains full Q4 protection; implementing the waiver as an encounter-scoped flag makes PVP-V5 fail.
9. **Overwhelm exclusivity** — in any situation where the Q4 cap applies, binding severance is impossible;
   the two can never both fire (§6).
10. **Grace** — a freshly re-incarnated PC cannot be attacked in a contested zone for
    `grace_fiction_minutes`; attacking during one's own grace forfeits it immediately (§5.1).
11. **Grace is predicate-enforced (bite test)** — moving the grace check to damage application makes
    PVP-V7 fail, proving the guard is not merely decorative.
12. **No side door (bite test)** — an admin or scripted attempt to create a PC-on-PC `combat_session`
    without passing §5 trips PVP-V4.
13. **Notoriety** — a `ContestedZone` kill emits full REP_001 notoriety; the same kill against a highly
    notorious victim emits less; a `Spar` emits none (§7).
14. **No loot roll** — a PvP kill produces **no** COMB_004 loot-table award; item movement occurs only via
    the Binding Contest (PVP-Q9).

---

## §14 — Deferred (PVP-D1..D8) · open questions

See the §1 "V1+ NOT shipping" table — each row is the corresponding `PVP-D*`. **No open questions.**

**Dependency to watch:** the Binding Contest's *sunder* path (COMB_004 §16) requires PL_007's
`durability` field, which is currently **`V1: ALWAYS None` (RES-D4, schema reservation only)**. Binding
degradation cannot ship until that reservation is activated — flagged in COMB_004 §16.4 and in the
combat index.

## §15 — Cross-references

- The decision this discharges — `PC-D2` in [`decisions/locked_decisions.md`](../../decisions/locked_decisions.md); reservation retired in [`02_world_authoring/_index.md`](../02_world_authoring/_index.md)
- **Item stakes** — [`COMB_004` §16 the Binding Contest](COMB_004_loot_and_spoils.md)
- Encounter spine + disparity cap + mortality — [`COMB_001`](COMB_001_combat_foundation.md) §6, Q3, Q4
- Formation + engagement predicate this mirrors — [`COMB_005`](COMB_005_encounter_spawning.md) §5, §6.1
- Death model — [`WA_006`](../02_world_authoring/WA_006_mortality.md) · Lex — [`WA_001`](../02_world_authoring/WA_001_lex.md)
- Places + safety band — [`PF_001`](../00_place/) · Notoriety — [`REP_001`](../00_reputation/) · Factions — [`FAC_001`](../00_faction/)
- Gank economics (already solved) — [`TDIL_001`](../17_time_dilation/) A1/A6
- Medium correction context — [`09_interaction_layer_reconciliation.md`](../../09_interaction_layer_reconciliation.md) · [`10_medium_blast_radius_audit.md`](../../10_medium_blast_radius_audit.md)
