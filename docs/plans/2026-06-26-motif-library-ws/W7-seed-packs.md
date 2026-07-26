# W7 — Seed Packs (detailed design)

> **Workstream:** W7 — *Seed packs (data-only, fully parallel)* of the narrative-motif-library feature.
> **Date:** 2026-06-26 · **Phase:** P1 (Wave 1). **Size:** **M** (data-heavy + one idempotent loader + one DB-write chokepoint; logic is shallow, breadth is the JSON content).
> **Spec:** [`docs/specs/2026-06-26-narrative-motif-library.md`](../../specs/2026-06-26-narrative-motif-library.md) — author against **§R1.4** (the corrected `motif` schema), **§2.4** (formalism→field map), **§15** (`scheme`/`info_asymmetry`).
> **Master plan:** [`docs/plans/2026-06-26-motif-library-master-plan.md`](../2026-06-26-motif-library-master-plan.md) §3 (F0 contract) + §4 W7.
> **Research:** [`docs/research/2026-06-26-narrative-control-formalisms.md`](../../research/2026-06-26-narrative-control-formalisms.md) (Propp/Greimas/oh-story 13-hooks/6-emotion-arcs/cultivation tropes) + the POC [`docs/research/2026-06-26-motif-prompt-control-poc.md`](../../research/2026-06-26-motif-prompt-control-poc.md) (validated tu-tiên / báo-thù / 宫斗 motifs).
> **Files OWNED (disjoint — no other WS edits these):** `services/composition-service/scripts/seed_motif_packs/*.json`, `services/composition-service/app/db/seed_motifs.py`, `services/composition-service/tests/unit/test_seed_motifs.py` (+ one integration test in `tests/integration/db/test_seed_motifs.py`).
> **Files READ ONLY (owned by F0 — W7 imports, never edits):** `app/db/migrate.py` (call-site wiring is a 1-line F0 change), `app/db/models.py` (`Motif`, `MotifBeat`, `MotifRole`, `MotifLink`), `app/config.py` (`motif_embed_model`).

---

## §1 Scope

Author the **system-tier seed library** for the two PO genres + an intrigue starter, abstracted onto the §R1.4 `motif` schema, plus the idempotent loader that writes them as the **only** sanctioned system-tier write path.

**In scope (W7 owns):**

1. **Two genre packs as data** — `cultivation.json` (tu-tiên) + `revenge.json` (báo-thù) — system-tier `motif` rows (`owner_user_id NULL`, `visibility='unlisted'` so the both-NULL CHECK passes; see §3.3), each row carrying:
   - `roles[]` = **Greimas actants** (`subject|object|sender|receiver|helper|opponent`) bindable to the book cast at plan-time (spec §2.4, research §2.2).
   - `beats[]` = **ordered Propp-style functional sub-beats**, each with `intent` + `tension_target` (1-5) + `order` (the §16 structural dial; the planner instantiates one scene per beat).
   - `preconditions[]` / `effects[]` = **plot-graph pre/post-conditions** (free-text NL — spec §11 "conditions = free-text NL for v1"; the planner matches semantically, no DSL). `effects` of motif N must be designed to satisfy `preconditions` of the legal successor (the `precedes` chain in §2 below).
   - `examples[]` = **AUTHOR-WRITTEN / synthetic** instantiations — **never source prose** (audit copyright guard; §6). One or two short lines that ground the abstract beat without naming any real work's cast.
   - `genre_tags[]`, `language`, `kind`, `category`, `summary`, `tension_target`, `emotion_target`.
2. **An intrigue starter** — a handful of `kind='scheme'` motifs for cung-đấu / 宫斗, each carrying the §15 `info_asymmetry` annotation (`{knows, deceived, gap}`) on the motif body (an `annotations` JSONB field on the row — see §3.5), validated by POC §6.
3. **The cross-formalism connective packs** — small system packs covering the oh-story **13 hook types** (`kind='hook'`) + **6 emotion-arc templates** (`kind='emotion_arc'`), so the library has genre-independent connective tissue the planner can attach to any beat (research §2.4 oh-story map).
4. **`db/seed_motifs.py`** — the idempotent loader: read the JSON packs, validate each row against the `Motif` model, INSERT with **deterministic UUIDv5** ids + `ON CONFLICT (id) DO NOTHING` (mirrors `_seed_builtin_templates`), **migrate-time only** (the system-write chokepoint, audit B-2). Also seeds the **system-tier `motif_link` `precedes` edges** that wire each genre's beat-chain into a legal-succession path.
5. **Tests** — every JSON row validates against `Motif`; the loader is idempotent (load twice → one copy); all seeded rows are system-tier (`owner_user_id IS NULL`); the `precedes` edges resolve to seeded codes; copyright lint (no banned source proper-noun in `examples[]`).

**Explicitly OUT of scope (other WS / later):**

- **The `motif` / `motif_link` DDL itself** → **F0** owns `migrate.py` schema. W7 only adds a *seed function* that F0's `run_migrations` calls (the call-site wire is a 1-line F0 edit; W7 hands F0 the function).
- **The platform embedding of seed rows** → **W3** owns `engine/motif_embed.py` + the `motif_embed_model` pipeline. Seed rows are written with `embedding = NULL`, `embedding_model = ''`; W3's back-fill embeds them (see §3.4 — this resolves the "embed at seed time" intent against the migrate-only reality).
- **`arc_template` seed content** → arc templates are **P4 (W10)**; W7 seeds **single motifs only** (P1 is single motifs per master plan §4 W2). The cultivation "three-year-pact" *arc* is represented in P1 as a **`composed_of` pattern motif** + its `precedes` chain, not an `arc_template` row (§2, note on `kind='pattern'`).
- **Mined / imported motifs** (`source='mined'|'imported'`) → W8/W9. W7 is `source='authored'` only.
- **CRUD/clone/catalog** → W1. W7 never exposes an HTTP surface.

---

## §2 Pack inventory (the deliverable's substance)

~30 motifs across cultivation + revenge + intrigue + the connective `hook`/`emotion_arc` packs. Below: `code` · `kind` · the beat-chain · the Greimas roles · the tension curve (per-beat `tension_target`) · one author-written example line. **POC-validated rows are tagged `[POC]`** (drafted/validated in the research POC §1-§8). A builder fills the JSON directly from these rows; the exact field shape is §3.2.

**Code naming convention (recommendation — see §7):** `genre.snake_case_motif` for `kind ∈ {sequence,situation,pattern,scheme}` (e.g. `cultivation.fortuitous_encounter`), and `kind.snake_case` for genre-independent connective motifs (e.g. `hook.cliff_question`, `emotion_arc.fall_then_rise`). `category` mirrors the code's dotted prefix (the Thompson-Motif-Index-style hierarchical id, spec §2.1) so retrieval can filter by `category LIKE 'cultivation.%'`.

### §2.1 Cultivation (tu-tiên) — `cultivation.json`

| # | code | kind | beat-chain (→ ordered) | roles (Greimas) | tension curve | author example |
|---|---|---|---|---|---|---|
| C1 `[POC]` | `cultivation.fortuitous_encounter` | sequence | isolation_after_fall → discover_relic → trial_by_legacy → receive_legacy(at_cost) | subject(protagonist), sender(dying_mentor/relic), object(technique/bloodline), opponent(absent) | 2→3→3→2 | "Cast into a sealed ravine, the weakling stumbles on a dying master who tests then gifts a forbidden art — bound by a debt." |
| C2 `[POC]` | `cultivation.closed_door_breakthrough` | sequence | seclusion → bottleneck → insight → tribulation → crisis → breakthrough | subject(protagonist), opponent(heaven/tribulation), helper(ally_guarding_door) | 2→3→3→4→5→4 | "Sealed away to break a stagnant rank, the cultivator faces an inner wall, a heavenly trial, near-death, then ascends a realm." |
| C3 `[POC]` | `cultivation.face_slap` | situation | arrogant_party_mocks → MC_underestimated → hidden_power_revealed → humiliation_reversal | subject(protagonist), opponent(arrogant_genius), receiver(witnesses) | 2→2→4→5 | "A preening heir sneers at the 'trash'; mid-contest the trash unveils a higher art and the heir is publicly broken." |
| C4 | `cultivation.trash_to_genius` | pattern | hidden_affliction → affliction_explained → affliction_becomes_gift → vindication | subject(protagonist), sender(diagnostician/elder), opponent(scornful_clan) | 2→3→4→5 | "The body called 'crippled' is revealed to host a rare constitution; the very flaw becomes the engine of ascent." |
| C5 | `cultivation.dao_heart_temper` | sequence | inner_demon_surfaces → false_memory_trial → confront_self → emerge_resolute | subject(protagonist), opponent(inner_demon), object(dao_heart) | 3→4→5→3 | "An illusory trial replays the cultivator's worst guilt; only by refusing the comforting lie does the dao-heart hold." |
| C6 | `cultivation.auction_house_treasure` | situation | rare_item_surfaces → bidding_war → rival_outbid → secret_means_to_win | subject(protagonist), opponent(wealthy_rival), object(treasure), helper(hidden_backer) | 2→3→3→4 | "A relic surfaces at auction; outspent and mocked, the protagonist wins it by a means none expected." |
| C7 | `cultivation.sect_entrance_trial` | sequence | arrive_unknown → underestimated_at_test → exceed_the_measure → recruited_with_stakes | subject(protagonist), sender(sect_elder), opponent(gatekeeper_disciple) | 2→2→4→3 | "An unranked outsider shatters the testing-stone's ceiling; the elders fight to claim them." |
| C8 | `cultivation.life_and_death_duel` | situation | challenge_issued → stakes_sworn → duel_turns → fatal_reversal | subject(protagonist), opponent(rival), receiver(crowd) | 3→3→4→5 | "A duel to the death on the arena; the favored son loses the instant he thinks he has won." |
| C9 | `cultivation.bottleneck_resource_hunt` | sequence | rank_stalls → resource_named → perilous_acquisition → consume_and_advance | subject(protagonist), object(spirit_herb/core), opponent(guardian_beast) | 2→3→4→3 | "Stuck below a wall, the cultivator hunts a guarded essence into a deadly range and breaks through on its power." |
| C10 | `cultivation.master_disciple_debt` | situation | rescued_or_taught → unpayable_debt_incurred → debt_called_in → loyalty_test | subject(protagonist), sender(master), object(obligation) | 1→2→3→4 | "Saved by a reclusive master, the disciple owes a debt that is called due at the worst hour." |
| C11 | `cultivation.tribulation_ascension` | sequence | merit_accrued → heavens_take_notice → lightning_tribulation → ascend_or_fall | subject(protagonist), opponent(heavenly_tribulation), helper(ally_anchor) | 3→4→5→4 | "Power draws the heavens' wrath; nine waves of tribulation must be survived to ascend." |

### §2.2 Revenge (báo-thù) — `revenge.json`

| # | code | kind | beat-chain (→ ordered) | roles (Greimas) | tension curve | author example |
|---|---|---|---|---|---|---|
| R1 `[POC]` | `revenge.betrayal_to_exile` | sequence | trust_established → betrayal_sprung → fall_and_loss → exile_with_vow | subject(protagonist), opponent(betrayer/sworn_brother), receiver(lost_kin), object(vengeance) | 2→4→4→3 | "On the eve of triumph the closest ally turns; stripped of all and cast out, the survivor swears return." |
| R2 `[POC]` | `revenge.three_year_pact` | pattern | humiliation → fortuitous_encounter → bitter_ascent → breakthrough → return_and_reversal | subject(protagonist), sender(mentor), opponent(rival), helper(ally) | 2→3→3→4→5 | "Given three years to grow strong or die, the outcast trains in obscurity and returns to overturn the one who broke them." |
| R3 | `revenge.false_accusation` | situation | framed_for_crime → condemned_publicly → evidence_hidden → truth_unmasked | subject(protagonist), opponent(framer), sender(witness/clue), receiver(judging_body) | 3→4→2→5 | "Branded a traitor on planted proof, the accused endures disgrace until the true hand is dragged to light." |
| R4 | `revenge.patient_infiltration` | sequence | enter_under_false_name → earn_trust_inside → gather_leverage → strike_from_within | subject(protagonist/disguised), opponent(target_house), object(leverage), helper(inside_contact) | 2→2→3→5 | "Under a borrowed name the avenger climbs the enemy's own ranks, then turns their secrets against them." |
| R5 | `revenge.blood_debt_collection` | situation | locate_the_guilty → confront_with_proof → guilty_pleads_or_defies → exact_the_price | subject(protagonist), opponent(perpetrator), receiver(the_wronged_dead) | 3→4→4→5 | "One by one the avenger finds those who shared the crime and makes each answer for it." |
| R6 | `revenge.mercy_or_vengeance` | situation | enemy_at_mercy → reason_to_spare_surfaces → choice_forced → consequence_lands | subject(protagonist), opponent(broken_enemy), sender(moral_voice/kin) | 4→3→5→4 | "With the killer helpless, a reason to spare appears; the avenger's choice reshapes who they become." |
| R7 | `revenge.pyrrhic_victory` | sequence | final_confrontation → victory_achieved → hidden_cost_revealed → hollow_aftermath | subject(protagonist), opponent(arch_enemy), object(revenge_attained) | 4→5→4→2 | "The enemy falls at last — and in the silence after, the avenger sees what the years of hate have cost." |
| R8 | `revenge.usurped_inheritance` | situation | rightful_claim_stolen → cast_out_as_pretender → proof_of_lineage_sought → claim_reclaimed | subject(protagonist), opponent(usurper), object(birthright), sender(loyal_retainer) | 2→3→3→5 | "A stolen birthright and a forged will leave the true heir a beggar — until the proof none could destroy resurfaces." |

### §2.3 Intrigue / cung-đấu (宫斗) starter — `intrigue.json`

All `kind='scheme'`, each carries an `info_asymmetry` annotation (§3.5). Schemes **chain** via `precedes` (a scheme's `effects` flip a thread advantage that seeds the next; spec §15.1). Validated end-to-end by POC §6 (12-beat 5-thread intrigue arc held on a weak model).

| # | code | kind | beat-chain (→ ordered) | roles | info_asymmetry (knows / deceived / gap) | tension curve | author example |
|---|---|---|---|---|---|---|
| I1 `[POC]` | `intrigue.planted_evidence_scheme` | scheme | plant_false_proof → bait_victim_to_act → victim_acts_on_false_belief → deniable_reveal → counter | subject(schemer), opponent(victim), helper(unwitting_agent), receiver(authority) | knows:[schemer] / deceived:[victim, authority] / gap:"the authority believes the victim is the culprit; the proof was planted" | 2→3→4→3→4 | "A doctored ledger is slipped where the rival will find and 'expose' it — walking straight into the trap that names them." |
| I2 `[POC]` | `intrigue.feigned_alliance` | scheme | offer_alliance → share_partial_truth → ally_relies_on_it → betray_at_pivot → realign | subject(schemer), receiver(false_ally), object(advantage) | knows:[schemer] / deceived:[false_ally] / gap:"the ally thinks they share a goal; the schemer plans to discard them at the pivot" | 2→2→3→5→3 | "An earnest pact, a shared secret just true enough to trust — until the moment it pays to break it." |
| I3 | `intrigue.whisper_campaign` | scheme | seed_rumor → rumor_spreads → target_isolated → patron_withdraws_support | subject(schemer), opponent(target), receiver(court/board) | knows:[schemer] / deceived:[court, patron] / gap:"the court believes the rumor is independent; one source authored it" | 2→3→3→4 | "A single planted doubt, repeated by mouths that don't know its origin, until the target stands alone." |
| I4 | `intrigue.loyalty_test_trap` | scheme | stage_a_temptation → observe_response → loyal_pass_or_fail → reward_or_purge | subject(power_holder), object(loyalty_proof), opponent(suspected_traitor) | knows:[power_holder] / deceived:[tested_party] / gap:"the tested party thinks the opportunity is real; it is a staged trap" | 2→3→4→4 | "A door left invitingly open is really a test; who steps through reveals exactly what the watcher needed to know." |
| I5 | `intrigue.double_agent_reveal` | scheme | trusted_insider_acts → small_inconsistency_noted → trap_set_to_confirm → unmask_and_turn | subject(protagonist), opponent(mole), helper(confidant) | knows:[protagonist (suspects)] / deceived:[the mole, the household] / gap:"the household trusts the insider; the protagonist has quietly confirmed the leak" | 3→3→4→5 | "A leak too precise to be chance; a baited false secret proves who carries tales — and to whom." |
| I6 | `intrigue.scapegoat_substitution` | scheme | crime_must_be_pinned → frame_a_lesser_party → evidence_steered → true_actor_walks_free | subject(schemer), opponent(scapegoat), receiver(investigators) | knows:[schemer] / deceived:[investigators, scapegoat] / gap:"the investigators believe the scapegoat acted; the true actor arranged it" | 3→4→3→4 | "When blame must land somewhere, the clever hand makes sure it lands on someone else." |

> **Why a `scheme`-specific shape works:** POC §6.1 showed the weak model held a 12-beat intrigue arc *only because* the template carried `scheme` + `info_asymmetry`. The seed encodes the gap as data so the conformance judge (W5) can later check the realized scene actually *exploits* it (spec §15.1, §14.4). The `alliance_shift` annotation (spec §15.2) is attached to I2/I6 via the row's `annotations.alliance_shift` (optional; §3.5).

### §2.4 Connective: oh-story 13 hook types — `hooks.json` (`kind='hook'`)

Genre-independent chapter-ending hooks (research §2.4 / oh-story `钩子技法`). Each is a **single-beat** motif (`beats[]` has one entry, the hook move) the planner can attach to any chapter's last scene. `roles[]` is usually just `subject` (the POV) + an optional `opponent`. `tension_target` is the ending spike. `emotion_target` names the pull (`suspense`, `dread`, `anticipation`).

| # | code | the hook move | tension | emotion_target |
|---|---|---|---|---|
| H1 | `hook.cliff_question` | end on an unanswered danger ("what was behind the door?") | 5 | suspense |
| H2 | `hook.sudden_reversal` | a last-line fact flips the scene's meaning | 5 | shock |
| H3 | `hook.impending_threat` | a named danger is now inbound, not yet arrived | 4 | dread |
| H4 | `hook.revelation_drop` | a secret is half-revealed, withheld at the cut | 4 | curiosity |
| H5 | `hook.dialogue_bomb` | a line of dialogue detonates and the chapter ends | 5 | shock |
| H6 | `hook.countdown_started` | a deadline/timer is set ("three days") | 4 | anticipation |
| H7 | `hook.unexpected_arrival` | a person who should not be here walks in | 4 | tension |
| H8 | `hook.choice_forced` | the POV is cornered into an irreversible decision | 4 | anxiety |
| H9 | `hook.power_glimpsed` | a hidden capability flashes, unexplained | 4 | anticipation |
| H10 | `hook.betrayal_hinted` | a trusted figure shows a crack of doubt | 3 | unease |
| H11 | `hook.mystery_deepened` | a new clue contradicts the assumed answer | 3 | curiosity |
| H12 | `hook.loss_imminent` | something the POV loves is about to be taken | 5 | dread |
| H13 | `hook.identity_teased` | a hint at someone's true name/role, unresolved | 4 | intrigue |

> Authoring note: `examples[]` for hooks are one synthetic last-line each (e.g. H1: "The seal was already broken — and the cell beyond it was empty."). `preconditions`/`effects` stay light (`preconditions: ["a scene in progress"]`, `effects: ["reader carried into the next chapter"]`) — hooks are connective, not plot-graph nodes, so they do **not** participate in `precedes` chains.

### §2.5 Connective: oh-story 6 emotion-arc templates — `emotion_arcs.json` (`kind='emotion_arc'`)

The 6 reusable emotional-shape modules (research §2.4 `情绪设计`; the Reagan/oh-story curve set), mapped to the −9…+9 emotion marker as a `tension_target` band + an `emotion_target` label. Each is a **multi-beat shape** (the emotional arc across a unit), `roles[]` = `subject` only (emotion is POV-bound), and is the **stylistic/structural bridge** the planner can overlay on a genre motif.

| # | code | shape (beats) | curve | emotion_target |
|---|---|---|---|---|
| E1 `[POC]` | `emotion_arc.fall_then_rise` | comfort → loss → struggle → triumph | 2→1→3→5 | catharsis (man-in-hole) |
| E2 | `emotion_arc.rise_then_fall` | ascent → peak → flaw_surfaces → downfall | 3→5→4→2 | tragedy (Icarus) |
| E3 | `emotion_arc.steady_rise` | start_low → repeated_wins → arrival | 2→3→4→5 | triumph (rags-to-riches) |
| E4 | `emotion_arc.steady_fall` | start_high → erosions → collapse | 4→3→2→1 | despair |
| E5 | `emotion_arc.dread_to_relief` | unease → mounting_fear → climax → release | 3→4→5→2 | relief |
| E6 | `emotion_arc.hope_to_heartbreak` | hope_kindled → near_success → cruel_turn → grief | 3→4→5→2 | heartbreak |

> These overlay, not replace, a genre motif: a `cultivation.closed_door_breakthrough` (C2) bound to `emotion_arc.fall_then_rise` (E1) tells the planner *both* the plot beats *and* the emotional shape. The overlay relationship is a `motif_link kind='variant_of'`? No — it is a **composition hint** the planner reads; W7 does **not** seed a hard link between an emotion_arc and every genre motif (combinatorial). Emotion arcs stand alone in the library; the planner/author pairs them at bind-time.

### §2.6 System `motif_link` seed edges (`precedes` legal-succession + `composed_of` patterns)

W7 also seeds the **system-tier edges** that make the genre packs walkable by the planner (spec §2.2). Two link kinds are seeded; **all endpoints are seeded system motifs** (the same-tier rule, audit H-2 — a system link may only touch system motifs):

- **`precedes` (legal succession)** — wire each genre's natural chain so motif N's `effects` feed motif N+1's `preconditions`:
  - cultivation: `fortuitous_encounter → closed_door_breakthrough → face_slap` (the canonical rise loop); `bottleneck_resource_hunt → closed_door_breakthrough`; `sect_entrance_trial → life_and_death_duel`.
  - revenge: `betrayal_to_exile → three_year_pact → face_slap`(cross-genre to cultivation, both system) → `pyrrhic_victory`; `false_accusation → patient_infiltration → blood_debt_collection`.
  - intrigue: `planted_evidence_scheme → feigned_alliance → double_agent_reveal` (the nesting scheme cycle, POC §6); `whisper_campaign → scapegoat_substitution`.
- **`composed_of` (pattern → members)** — the two `kind='pattern'` rows expand to their member sequence motifs:
  - `revenge.three_year_pact` (R2) → [`humiliation`-as-`betrayal_to_exile`(R1), `fortuitous_encounter`(C1), `closed_door_breakthrough`(C2), `face_slap`(C3)] with `ord` 1..4. This is how the POC's "three-year-pact arc" lives in P1 **without** an `arc_template` row (those are P4).
  - `cultivation.trash_to_genius` (C4) → [`fortuitous_encounter`(C1), `closed_door_breakthrough`(C2), `face_slap`(C3)] ord 1..3.

> The link rows get their own deterministic UUIDv5 ids (namespace `…:link`, name = `from_code|to_code|kind`) so they are idempotent under `ON CONFLICT (from_motif_id,to_motif_id,kind) DO NOTHING` (the schema's UNIQUE). F0's `motif_link` carries a **cycle guard** on `precedes`; the seed chains above are acyclic by construction — a test asserts it (§5).

**Inventory total:** 11 (cultivation) + 8 (revenge) + 6 (intrigue) + 13 (hooks) + 6 (emotion arcs) = **44 motif rows** + ~14 `precedes` edges + 2 `composed_of` expansions (≈7 member edges). Comfortably ≥ the 20-30 ask; the connective packs (hooks/emotion arcs) are cheap and high-leverage. If the PO wants P1 leaner, the **minimum viable seed** is the 5 `[POC]` rows + their `precedes` chain (the rows the planner eval-gate exercises); the rest can land in a follow-up seed without a schema change (idempotent additive load).

---

## §3 The seed mechanism

### §3.1 Where it runs — migrate-time only (the system-write chokepoint, audit B-2)

`seed_motifs.py` exposes one coroutine, `seed_motifs(conn)`, called **once** from F0's `run_migrations()` right after the schema applies and after `_seed_builtin_templates` — exactly the `structure_template` precedent ([migrate.py](../../../services/composition-service/app/db/migrate.py) §M1). There is **no runtime/API path** that inserts a system-tier (`owner_user_id IS NULL`) motif. Combined with F0's DB `CHECK (owner_user_id IS NOT NULL)` on the user-write repo path and the user CRUD server-stamping `owner_user_id = JWT.sub`, this makes migrate-time seeding the *only* way a both-NULL row is ever born (B-2 held structurally, not by convention).

```python
# app/db/seed_motifs.py  (W7 owns)
async def seed_motifs(conn: asyncpg.Connection) -> int:
    """Idempotently seed the system-tier motif library from scripts/seed_motif_packs/*.json.
    Returns the number of motif rows present after seeding (for the migrate log line).
    SYSTEM-WRITE CHOKEPOINT (audit B-2): the ONLY path that writes owner_user_id IS NULL."""
    rows = _load_and_validate_packs()          # parse JSON → Motif models (raises on a bad row)
    links = _load_link_edges(rows)             # build precedes/composed_of from the manifest
    async with conn.transaction():
        for m in rows:
            await conn.execute(_INSERT_MOTIF_SQL, m.id, m.code, m.language, m.visibility,
                               m.kind, m.category, m.name, m.summary, m.genre_tags,
                               _j(m.roles), _j(m.beats), _j(m.preconditions), _j(m.effects),
                               m.tension_target, m.emotion_target, _j(m.examples),
                               _j(m.annotations), m.source, m.source_version)
            # owner_user_id, embedding, embedding_model are NOT passed → DEFAULT NULL/''
        for ln in links:
            await conn.execute(_INSERT_LINK_SQL, ln.id, ln.from_id, ln.to_id, ln.kind, ln.ord)
    return await conn.fetchval("SELECT count(*) FROM motif WHERE owner_user_id IS NULL")
```

`_INSERT_MOTIF_SQL` = `INSERT INTO motif (id, code, language, visibility, kind, category, name, summary, genre_tags, roles, beats, preconditions, effects, tension_target, emotion_target, examples, annotations, source, source_version) VALUES ($1,…,$19::jsonb,…) ON CONFLICT (id) DO NOTHING` — `owner_user_id` omitted ⇒ stays NULL (system tier).

> **F0 call-site wire (1-line, F0 owns the edit — W7 supplies the function):**
> ```python
> # in migrate.py run_migrations(), after _seed_builtin_templates(conn):
> from app.db.seed_motifs import seed_motifs
> n_motifs = await seed_motifs(conn)
> logger.info("composition migrate: … + %d system motifs seeded", n_motifs)
> ```
> This is the **only** thing W7 needs from F0 beyond the schema; it is named here so the F0/W7 seam is explicit and reviewable. If F0 prefers, `seed_motifs` can be registered via a list F0 iterates — either way the *content + loader* is W7, the *call* is F0.

### §3.2 Deterministic UUIDs + `language` tag

Mirror `BUILTIN_TEMPLATES`' deterministic-id idempotency, but generate ids **from the code+language** with `uuidv5` (Python `uuid.uuid5`) under a fixed namespace, rather than hand-writing literal UUIDs (44 rows + edges is too many to hand-curate safely, and a typo'd literal is a silent dup):

```python
_MOTIF_NS = uuid.UUID("6d0746f0-0000-5000-8000-000000000001")  # fixed W7 namespace (any constant UUID)
def _motif_id(code: str, language: str) -> uuid.UUID:
    return uuid.uuid5(_MOTIF_NS, f"motif|{language}|{code}")
def _link_id(from_code, to_code, kind, language) -> uuid.UUID:
    return uuid.uuid5(_MOTIF_NS, f"link|{language}|{from_code}|{to_code}|{kind}")
```

- **Deterministic** → re-running migrate produces the *same* id → `ON CONFLICT (id) DO NOTHING` is a true no-op (idempotent across restarts, audit-friendly).
- **`language` in the id key** → matches the schema's dedup/embed key `(code, language)` (spec §R1.1.3). Seeding the same motif in `vi` and `en` yields two distinct rows with distinct ids — no collision, and the `uq_motif_system (code, language) WHERE owner_user_id IS NULL` partial is satisfied. (See §7 for the vi-vs-en first decision.)
- **Stable** → the id is a pure function of `(code, language)`; renaming a `name`/`summary` does **not** move the id (only `code` is identity, consistent with the schema's `code` = "stable cross-tier identity").

> Note vs. F0 schema default `DEFAULT uuidv7()`: W7 **supplies** the id explicitly (uuid5), so the column default never fires for seed rows — identical to how `BUILTIN_TEMPLATES` passes a literal `id`. uuid5 (v5) vs the column's v7 default is fine; the PK only requires uniqueness, and an explicit insert id overrides the default.

### §3.3 `visibility` on a system row — the both-NULL CHECK

§R1.4 adds `CONSTRAINT motif_user_owned CHECK (owner_user_id IS NOT NULL OR visibility <> 'private')` — "a both-NULL row must be a published/system row, never a private orphan." So seed rows (`owner_user_id NULL`) **must not** be `visibility='private'`. W7 sets seeded system rows to **`visibility='unlisted'`** (visible to everyone via the read predicate's `owner_user_id IS NULL` branch, but not surfaced in the public `catalog` projection unless deliberately set `public`). This satisfies the CHECK and keeps the system library discoverable-by-the-planner without dumping 44 rows into the public catalog. *(Alternative: `public` — rejected for P1; we don't want the seed flooding the public catalog/discovery surface before catalog UX exists. `unlisted` is the correct default; a later admin action can promote chosen rows to `public`.)*

### §3.4 Embedding — written NULL at seed, back-filled by W3 (resolves the "embed at seed time" intent)

The spec §R1.1.2 wants "the platform-embed happens at seed time (embedding_model = the fixed motif_embed_model)." **Reality check against the migrate-only chokepoint:** the seed runs inside `run_migrations` at **service boot**, where (a) there is no user/JWT/BYOK context, and provider-registry's `/internal/embed` is **per-user** ([embedding_client.py](../../../services/composition-service/app/clients/embedding_client.py) takes `user_id`), and (b) provider-registry may be **down** at boot — and a migration must never block boot on an optional dependency (the exact C16 lesson in migrate.py: "writing/Generate is never wall-blocked by an optional dependency").

**Resolution (W7 + W3 seam — documented here, implemented by W3):**
- W7 seeds every motif row with **`embedding = NULL`, `embedding_model = ''`** (the `reference_source` precedent: "embedding is NULL only transiently … a null-vector row is simply never a search hit").
- **W3 owns the platform-embed back-fill** (`engine/motif_embed.py`): a lazy pass that embeds any `embedding IS NULL` system motif with the fixed `motif_embed_model` (resolved as a **platform** model_source, not a user BYOK — this is the one place `motif_embed_model` config means "platform credential", and W3 wires the provider-registry platform path). It runs on first retrieval-touch or a startup background task — **not** in the migrate transaction.
- **Why this is correct, not a workaround:** seeding is *content*; embedding is *derived* and *model-dependent*. Coupling them would (1) wall boot on provider-registry, (2) bake a model choice into migrate-time, (3) duplicate W3's embed pipeline in W7. The `embedded_summary_hash` staleness guard (schema) means a later `summary` edit re-embeds anyway — so NULL-at-seed + lazy-fill is the same machinery, just with the initial hash empty. **W7's contract test asserts seed rows are NULL-embedding**; W3's contract test asserts the back-fill populates them with a single shared `embedding_model`.

> This is the one place W7's design **diverges from a literal reading of the spec** (embed-at-seed-time). It is called out explicitly for the PO/F0 review: the divergence is forced by the migrate-only chokepoint + the per-user/optional-dependency nature of provider-registry, and it lands the *same* end state (all system vectors share the platform model) via W3's existing pipeline. If F0/PO insist on embed-at-seed, the only correct way is a **separate post-boot seed-embed job** (still not in the migrate tx) — which is exactly the W3 back-fill. Recommendation: keep embedding in W3.

### §3.5 The `info_asymmetry` / `annotations` field on a scheme row

§15.1 puts `info_asymmetry` "on a scheme motif / its application." For the **library row** (W7's concern), the schema §R1.4 `motif` table has no dedicated `info_asymmetry` column, but `motif_application` has an `annotations JSONB` for the *bound* asymmetry. For the **seed**, the cleanest home is a motif-level **`annotations JSONB`** carrying the *template* asymmetry (the roles' knows/deceived pattern), which the planner copies into the application's `annotations` at bind-time. **Dependency on F0:** this requires `motif.annotations JSONB NOT NULL DEFAULT '{}'` to exist on the table. It is **not** in the §R1.4 `motif` DDL as written (only `motif_application` has `annotations`).

→ **W7 raises this to F0 as a contract addition** (see §7 open decisions): add `annotations JSONB NOT NULL DEFAULT '{}'` to `motif`. It is additive, idempotent, and needed by the `scheme` seed (and by W5 conformance, which checks the gap). If F0 declines, the fallback is to encode the asymmetry **inside the relevant `beats[]` entry** (each scheme beat already describes the false-belief move) as a `beat.info_asymmetry` sub-object — no new column, but less queryable. **Recommendation: the motif-level `annotations` column** (one small additive field, high value for intrigue + conformance). The Motif model (F0.2) gains `annotations: dict[str, Any] = {}` to match.

### §3.6 Pack file layout

```
services/composition-service/scripts/seed_motif_packs/
  cultivation.json      # 11 rows (§2.1)
  revenge.json          # 8 rows  (§2.2)
  intrigue.json         # 6 scheme rows (§2.3)
  hooks.json            # 13 hook rows (§2.4)
  emotion_arcs.json     # 6 emotion_arc rows (§2.5)
  links.json            # the precedes + composed_of edges (§2.6), referenced by code
```

Each genre file is a JSON array of motif objects. One object's shape (the C1 row, fully realized — this is the concrete JSON shape a builder copies):

```json
{
  "code": "cultivation.fortuitous_encounter",
  "language": "en",
  "kind": "sequence",
  "category": "cultivation.encounter",
  "name": "Fortuitous Encounter → Legacy",
  "summary": "A humiliated weakling, isolated by a fall or banishment, discovers a relic or dying master, is tested, and receives a hidden legacy at the cost of a binding debt.",
  "genre_tags": ["cultivation", "xianxia", "tu-tien", "progression"],
  "roles": [
    {"key": "protagonist", "actant": "subject",  "label": "the isolated weakling", "constraints": "currently weak or disgraced"},
    {"key": "mentor",      "actant": "sender",   "label": "dying master / relic spirit", "constraints": "near death or dormant"},
    {"key": "legacy",      "actant": "object",   "label": "the inherited art or bloodline", "constraints": "forbidden or peerless"}
  ],
  "beats": [
    {"key": "isolation",    "label": "Isolation after the fall", "intent": "strand the protagonist beyond help, at their lowest", "tension_target": 2, "order": 1},
    {"key": "discovery",    "label": "Discover the relic/master", "intent": "the chance encounter that changes everything", "tension_target": 3, "order": 2},
    {"key": "trial",        "label": "Trial by the legacy",       "intent": "the mentor/relic tests worthiness", "tension_target": 3, "order": 3},
    {"key": "inheritance",  "label": "Receive the legacy at a cost", "intent": "grant power bound to a debt or secret", "tension_target": 2, "order": 4}
  ],
  "preconditions": ["the protagonist is weak, humiliated, or cast out", "no allies are present"],
  "effects": ["the protagonist gains a hidden power or technique", "a debt or secret tie to the mentor is created"],
  "tension_target": 3,
  "emotion_target": "hope",
  "examples": [
    "Cast into a sealed ravine, the weakling stumbles on a dying master who tests then gifts a forbidden art — bound by a debt of loyalty."
  ],
  "annotations": {},
  "source": "authored",
  "source_version": 1
}
```

`links.json` shape (one edge):
```json
{"from_code": "cultivation.fortuitous_encounter", "to_code": "cultivation.closed_door_breakthrough", "kind": "precedes", "ord": 1}
```
`composed_of` edge:
```json
{"from_code": "revenge.three_year_pact", "to_code": "revenge.betrayal_to_exile", "kind": "composed_of", "ord": 1}
```

The loader resolves `from_code`/`to_code` → seeded `_motif_id(code, language)` (the language is the manifest's default, `en` for the first cut) to fill `from_motif_id`/`to_motif_id`.

---

## §4 Quality bar + the PO-review gate

W7 is the **P1-headline deliverable** — the planner's value is bounded by seed quality (a bland/wrong motif library yields bland/wrong plans). The bar:

**Content quality bar (every row):**
1. **Abstracted, not copied** — roles are slots (subject/sender/object…), beats are generic moves ("isolation by disaster"), and **no `examples[]` line names any real work's cast, place, or proper noun** (the copyright guard, §6). A row that reads like a retelling of a specific novel fails.
2. **Greimas-valid roles** — every motif declares at least a `subject`; relational motifs declare the `opponent`/`sender` the plot needs (research §2.2). A motif with zero roles is rejected (the planner has nothing to bind).
3. **Walkable conditions** — `effects[]` of a motif that `precedes` another must plausibly satisfy that successor's `preconditions[]` (free-text, judged by a human at review; the planner matches semantically). The `precedes` chains in §2.6 are designed to hold.
4. **Coherent tension curve** — per-beat `tension_target` rises/falls in a way that matches the motif's dramatic shape (e.g. `face_slap` peaks at the reveal, beat 4 = 5). The overall `tension_target` ≈ the curve's peak/mean.
5. **Genre-faithful** — a cultivation reader recognizes C1-C11 as real tu-tiên beats; a 宫斗 reader recognizes I1-I6. This is the axis only the PO can sign off (below).

**The PO-review gate (the genres' author signs the content):**
- **The PO writes tu-tiên + báo-thù + cung-đấu** — they are the domain authority. W7's content is **not "done" until the PO reviews the pack content** (master-plan §4 W7 eval-gate: "the PO reviews the pack content"). This is a **POST-REVIEW human checkpoint** specific to W7: present the rendered packs (name + summary + beat-chain + example per row) as a readable table; the PO accepts / edits / rejects per row.
- **What the PO checks:** genre-faithfulness (#5), example quality (do they read like a craft-guide illustration, not a plagiarized passage), missing staples (a genre beat the author expects that the pack lacks), and the `vi`-vs-`en` language call (§7).
- **Mechanics:** the review is on the **JSON content**, not the code — so it can happen in parallel with W1-W6 building, and edits are data-only (no rebuild). A rejected row is removed or rewritten in the JSON; the loader's idempotency means re-seeding after an edit is safe (the id is stable per `code`; an edited `summary` re-inserts as a no-op on `ON CONFLICT (id)` — **note**: an *edit* to an existing seeded row's `summary` will **not** overwrite via `ON CONFLICT (id) DO NOTHING`; see §5 idempotency caveat + the `--reseed` path for dev).

---

## §5 Tests (`tests/unit/test_seed_motifs.py` + one integration test)

Pure-data + loader tests (no DB) in `tests/unit/`, plus one real-Postgres idempotency test in `tests/integration/db/` gated on `TEST_COMPOSITION_DB_URL` (the `test_migrate.py` precedent).

**Unit (no DB — validate the content + the id logic):**
1. `test_every_pack_row_validates_against_motif_model` — load all `*.json`, construct `Motif(**row)` for each; any schema mismatch (bad `kind`, missing `name`, role missing `actant`, `tension_target` out of 1-5) fails. **This is the F0-contract guard** — if F0 changes a field name, this test breaks immediately (the contract test for W7).
2. `test_codes_unique_per_language` — no two rows share `(code, language)` (would collide on the system partial). Also asserts `code` matches the naming convention regex (`^[a-z_]+\.[a-z_]+$` for genre motifs / `^(hook|emotion_arc)\.[a-z_]+$` for connective).
3. `test_kind_matches_pack` — cultivation/revenge rows are `kind ∈ {sequence,situation,pattern}`; intrigue rows are `kind='scheme'` and carry a non-empty `annotations.info_asymmetry` with `knows`/`deceived`/`gap`; hooks `kind='hook'`; emotion arcs `kind='emotion_arc'`.
4. `test_beats_ordered_and_nonempty` — every motif has ≥1 beat; `beats[].order` is 1..N contiguous; every beat has an `intent`.
5. `test_roles_have_subject` — every motif declares a `subject` actant; every `actant` is in the Greimas set.
6. `test_deterministic_ids_stable` — `_motif_id(code, lang)` is pure (same input → same UUID across calls); two different codes → different ids; `vi` vs `en` of the same code → different ids.
7. `test_link_endpoints_resolve` — every `links.json` `from_code`/`to_code` names a motif present in the loaded packs (no dangling edge); `composed_of` parents are `kind='pattern'`.
8. `test_precedes_chains_acyclic` — the `precedes` graph over seeded codes has no cycle (matches F0's `motif_link` cycle guard; a seed that violated it would be rejected at insert, so catch it here first).
9. `test_examples_have_no_banned_proper_nouns` — the **copyright lint** (§6): assert no `examples[]` string contains any token from a curated banned-list of well-known source proper nouns (e.g. names of famous xianxia protagonists/sects/works the packs are *inspired by* but must not name). The list lives next to the test; a hit fails the build with the offending row+token.
10. `test_all_seed_rows_are_system_tier` — no loaded row carries an `owner_user_id` key (the JSON must never set ownership; system tier is enforced by *omission* + the NULL default).
11. `test_no_seed_row_is_private` — every row's `visibility` is `unlisted` (or `public`), never `private` (the both-NULL CHECK, §3.3).

**Integration (real Postgres — idempotency + tier + the chokepoint):**
12. `test_seed_idempotent_and_system_tier` — run `seed_motifs(conn)` twice; assert `count(*) WHERE owner_user_id IS NULL` equals the pack row count **after both runs** (no double-insert); assert the `motif_link` edges seed once; assert a re-run logs the same count. Mirrors `test_migrate_idempotent_and_seeds_once`.
13. `test_seed_rows_have_null_embedding` — assert every seeded row has `embedding IS NULL` and `embedding_model = ''` (the W3-back-fill contract, §3.4 — proves W7 does **not** embed).
14. `test_seeded_links_respect_same_tier` — every seeded `motif_link` endpoint is a system motif (`owner_user_id IS NULL` on both `from`/`to`) — the audit H-2 same-tier rule, proven on the seed data.

**Idempotency caveat (documented + a dev `--reseed`):** `ON CONFLICT (id) DO NOTHING` means an **edit to an already-seeded row** (changing `summary`/`beats` after it's in a DB) is **not** applied on the next boot — the id is stable, so the old row stays. This is correct for production (the seed never silently mutates a row a user may have cloned). For **dev iteration** during W7 authoring, `seed_motifs.py` gets a guarded `reseed=False` param that, when true (CLI/dev only, never in `run_migrations`), does `INSERT … ON CONFLICT (id) DO UPDATE SET … WHERE motif.source='authored'` — only ever touching system authored rows, never a user row. Production boot always calls `seed_motifs(conn)` with `reseed=False`. A test asserts `run_migrations` never passes `reseed=True`.

---

## §6 Audit risk-guards W7 owns

| Guard | Risk | How W7 holds it |
|---|---|---|
| **B-2 — system writes ONLY via the migrate-only chokepoint** | a runtime path creating a both-NULL (system) row = the kinds-bug class (any user mutating shared rows) | `seed_motifs()` is called **only** from `run_migrations` (boot), inserts with `owner_user_id` **omitted** (NULL by default), and has **no caller** in any router/MCP/worker. Test #12 + #10 prove tier; the absence of any non-migrate caller is the structural guarantee. The user-write CHECK (`owner_user_id IS NOT NULL`) is F0's, but it *complements* W7: together, a system row can be born **nowhere else**. |
| **Copyright — examples author-written/synthetic, never source prose** (spec §12.6, §11) | a seeded `examples[]` could smuggle a near-verbatim passage / name a real work → substantial-similarity exposure | Every `examples[]` line is **authored fresh** (abstract illustration of the beat). Test #9 lints against a banned proper-noun list. The `roles`-as-slots + generic-beats schema structurally prevents a row from *being* a retelling (it has no proper nouns by construction). Authoring rule in §4 #1 + the PO review (§4) double-check. **`source='authored'` on every W7 row** (never `imported`) — so the §R1.3 examples-strip-on-publish trigger (for imported-derived motifs) is moot here, but the seed independently guarantees clean examples. |
| **B-2 corollary — seeded links touch only system motifs** (audit H-2) | a system `motif_link` pointing at a user motif would let a user's edit affect the system graph | Seed `links.json` references only seeded codes; test #14 proves both endpoints are `owner_user_id IS NULL`. F0's "user-created edges may not touch system motifs" rule is the reverse direction; W7 holds the system→system direction. |
| **Tenancy default — no `private` system orphan** (§R1.4 CHECK) | a both-NULL `private` row violates the CHECK → migrate fails | All seed rows `visibility='unlisted'`; test #11. |

---

## §7 Open micro-decisions + recommendation

| # | Decision | Options | Recommendation |
|---|---|---|---|
| **D1** | **Seed `vi` or `en` first?** | (a) `en` first; (b) `vi` first; (c) both now | **`vi` first, `en` immediately after as a sibling pack.** Rationale: the PO writes Vietnamese tu-tiên/báo-thù/cung-đấu (their own genres) and is the reviewer — authoring + reviewing in `vi` is fastest and highest-fidelity; the platform is multilingual and `language` is in the dedup/embed key (§R1.1.3), so `en` is a **parallel pack with the same codes, `language:"en"`** (distinct ids via §3.2) added in the same PR or the next. Do **not** seed only `en` and machine-translate `vi` later — that re-keys after embed (the §R1.1.3 warning). *Pragmatic split:* if the build agent is more fluent authoring `en`, seed `en` first but **commit the `vi` pack in the same workstream** before the PO gate — the PO needs `vi` to review faithfully. **Net: both languages, `vi` is the source-of-truth authoring language, codes shared across languages.** |
| **D2** | **Code naming convention** | (a) `genre.motif`; (b) `motif_only`; (c) numeric ids | **`genre.snake_case_motif`** for genre motifs + **`kind.snake_case`** for connective (hook/emotion_arc), `category` = the dotted prefix (§2). Gives a Thompson-Motif-Index-style hierarchy (spec §2.1 `category`), lets retrieval filter `category LIKE 'cultivation.%'`, and keeps `code` human-readable + stable (identity key). Enforced by test #2's regex. |
| **D3** | **`annotations` column on `motif`?** (for scheme `info_asymmetry`) | (a) add `motif.annotations JSONB` (F0); (b) nest in `beats[]`; (c) skip asymmetry in seed | **(a) — ask F0 to add `motif.annotations JSONB NOT NULL DEFAULT '{}'`** (§3.5). One additive field, needed by the `scheme` seed *and* W5 conformance (which checks the gap). Fallback (b) if F0 declines. **This is the one F0-contract delta W7 requests** — flag it at the F0 freeze so it's in the frozen schema, not retrofitted. |
| **D4** | **Embed at seed time vs W3 back-fill** | (a) NULL-at-seed + W3 lazy back-fill; (b) embed inside migrate | **(a)** — forced by the migrate-only chokepoint + provider-registry being per-user/optional (§3.4). Lands the same end state via W3's pipeline. Embedding in the migrate tx would wall boot on an optional dependency (the C16 lesson). |
| **D5** | **Seed breadth for P1** | (a) all 44; (b) the 5 `[POC]` + chain only | **(a) all 44** (the connective hooks/emotion-arcs are cheap and give the planner genre-independent glue). The **minimum viable** fallback is (b) — the rows the eval-gate exercises — added-to later via idempotent load. No schema risk either way. |

---

## §8 Task list

1. **[F0 dependency — confirm before authoring]** Confirm the frozen §R1.4 `motif` schema + the `Motif`/`MotifBeat`/`MotifRole`/`MotifLink` model field names; **request the `motif.annotations JSONB` addition (D3)** at the F0 freeze. Confirm the `seed_motifs(conn)` call-site wire (§3.1) with F0.
2. **Author `cultivation.json`** — the 11 rows (§2.1), full JSON shape per §3.6, `vi` source-of-truth (D1). Validate each against `Motif` locally.
3. **Author `revenge.json`** — the 8 rows (§2.2), including R2 `three_year_pact` as a `kind='pattern'`.
4. **Author `intrigue.json`** — the 6 `scheme` rows (§2.3) with `annotations.info_asymmetry` (knows/deceived/gap) per row.
5. **Author `hooks.json` + `emotion_arcs.json`** — the 13 hooks (§2.4) + 6 emotion arcs (§2.5), single-/multi-beat, light conditions.
6. **Author `links.json`** — the `precedes` legal-succession chains + the 2 `composed_of` pattern expansions (§2.6); verify acyclicity + same-tier-by-construction.
7. **Write `db/seed_motifs.py`** — the loader (§3.1): `_load_and_validate_packs`, `_load_link_edges`, deterministic `_motif_id`/`_link_id` (§3.2), the transactional idempotent INSERTs (motifs then links), the `reseed` dev path (§5 caveat), the count return for the migrate log.
8. **Write `tests/unit/test_seed_motifs.py`** — tests #1-#11 (§5): model-validation contract test, code uniqueness+regex, kind/role/beat invariants, deterministic-id purity, link-endpoint resolution, acyclicity, the copyright proper-noun lint, system-tier-by-omission, no-private.
9. **Write `tests/integration/db/test_seed_motifs.py`** — tests #12-#14 (§5): idempotent double-seed + system-tier count, NULL-embedding contract (the W3 seam), seeded-links same-tier. Gate on `TEST_COMPOSITION_DB_URL`.
10. **Author the `en` sibling packs** (D1) — same codes, `language:"en"`, before the PO gate so the PO can review `vi` and the `en` parity exists.
11. **VERIFY** — run `pytest tests/unit/test_seed_motifs.py` (green, no DB); run the integration test against a throwaway DB if available, else `LIVE-SMOKE deferred to D-W7-SEED-LIVE-SMOKE` (the real cross-tier embed/retrieve smoke is R-NODE-P1, master-plan §6 — W7 alone has no cross-service surface, so `live infra unavailable` is a legitimate token if the stack isn't up).
12. **PO-REVIEW gate (§4)** — render the packs as a readable table (name · summary · beat-chain · example per row) and present to the PO for genre-faithfulness sign-off + the `vi`/`en` call; apply data-only edits per their feedback; re-seed (idempotent / `--reseed` in dev).
13. **SESSION + COMMIT** — update `docs/sessions/SESSION_HANDOFF.md` (W7 seed packs done, the D3 `annotations` ask to F0, the D4 embed-in-W3 seam, the `D-W7-SEED-LIVE-SMOKE` deferral if taken); commit the JSON + loader + tests together.

---

## §9 F0-contract dependencies (the seam, restated for the integrator)

W7 consumes from F0 and asks for one addition:

**Consumes (frozen, read-only):**
- `motif` table per §R1.4 — exact columns `id, owner_user_id, code, language, visibility, kind, category, name, summary, genre_tags, roles, beats, preconditions, effects, tension_target, emotion_target, examples, source, source_ref, source_version, embedding, embedding_model, …`.
- `motif_link` table — `id, from_motif_id, to_motif_id, kind ∈ {composed_of,precedes,variant_of}, ord` + the cycle guard + same-tier rule.
- `Motif` / `MotifBeat` / `MotifRole` / `MotifLink` Pydantic models (`db/models.py`) — the field names W7's JSON keys must match (test #1 is the contract test).
- The `run_migrations` call-site (F0 wires the 1-line `seed_motifs(conn)` call; W7 supplies the function).

**Requests (one additive F0 delta — D3):**
- `motif.annotations JSONB NOT NULL DEFAULT '{}'` + `Motif.annotations: dict = {}`, for the `scheme` `info_asymmetry` template (and W5 conformance). Additive, idempotent; flag at the F0 freeze.

**Hands to W3 (the embed seam — D4):**
- Seed rows ship `embedding = NULL`, `embedding_model = ''`. W3's `engine/motif_embed.py` back-fills them with the platform `motif_embed_model`. W7's test #13 asserts the NULL-at-seed half of the contract; W3's test asserts the back-fill half.
