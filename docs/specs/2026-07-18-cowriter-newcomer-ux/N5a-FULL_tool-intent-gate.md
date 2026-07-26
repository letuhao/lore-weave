# N5a-FULL — the tool-level intent gate (stop the co-writer's proactive world-setup)

> **Why this needs real investment.** The over-reach — asked for one chapter, the co-writer
> proactively adopts glossary standards and blocks the newcomer with an unrequested confirm — survived
> THREE surgical attempts (live-QC'd each): a persona restraint clause, removing `glossary_adopt_standards`
> from `ALWAYS_HOT_WRITES`, and excluding it from the domain hot-seed (`DISCOVER_ONLY_HIGH_IMPACT`). Every
> time, the model still reached it via `find_tools`/`tool_load`. **A determined model finds the tool no
> matter how quiet the default surface is.** So the fix cannot be "make it less prominent" — the tool must
> be **genuinely unreachable on a non-setup turn**, and reachable only when the user actually asks.

## The requirement (two-sided — both must hold)
1. **Plain writing turn** ("create Chapter 1 and write the opening") → `glossary_adopt_standards` is
   UNREACHABLE by the agent (not hot, not returned by `find_tools`, not loadable by `tool_load`). It creates
   the chapter and stops.
2. **Genuine setup turn** ("set up my world's lore categories" / "adopt fantasy standards") → the tool IS
   reachable and works. We must NOT break legitimate glossary/world setup.

The gate is therefore driven by **turn intent**, enforced at the reachability **chokepoint** (the one place
all of hot + find_tools + tool_load funnel through), using the **existing** intent-classification infra
(reuse the async skill router / embeddings — do not build a new classifier).

## Design (to be finalized from the 2 architecture maps)
- **Chokepoint:** the per-turn tool catalog that `find_tools`/`tool_load` search over. If a tool is absent
  from THAT catalog for the turn, no path can reach it. *(seam TBD — investigator 1.)*
- **Intent signal:** reuse the router's per-turn intent classification to decide "is this a world-setup
  request?" *(mechanism + cost TBD — investigator 2.)*
- **The tie:** the high-impact setup tools (`glossary_adopt_standards`, and likely the shaping/plan
  ontology tools) are present in the turn catalog ONLY when (a) the glossary skill is pinned, OR (b) the
  router classifies the turn as world-setup intent. Otherwise absent → unreachable.

## Candidate approaches (evaluate once seams are known)
- **A — Catalog filter on the shaping-skill signal:** I already split glossary into lean-core + pin/router-
  gated `glossary_shaping`. Tie the high-impact tools' catalog presence to `glossary_shaping` being injected
  (pinned OR router-added on intent). Cleanest if the catalog is filtered by injected skills' domains.
- **B — Explicit intent anchor:** embed the user message, compare to a canonical "set up world ontology"
  anchor, threshold; below threshold ⇒ filter the high-impact tools out of the turn catalog. Reuses the
  embedding client. Risk: false negatives (a real setup request phrased oddly) → user hits a "I can't reach
  that — try 'set up my world'" fallback; false positives → mild (setup tools available when not needed).
- **C — Deterministic + embedding hybrid:** cheap keyword pre-check (`set up|build|adopt|ontology|lore
  categor|glossary|world`) OR embedding match ⇒ enable. Fewer false negatives, still cheap.

## Risks / must-verify
- **Don't break legit setup** (requirement #2) — the two-sided QC is mandatory.
- **find_tools AND tool_load both gated** — a filter that only hides from find_tools but lets tool_load
  fetch by name is the exact hole that beat attempt #3. The chokepoint must cover both.
- **Cost** — if the gate adds an embedding call every turn, confirm the router already runs one (no new
  per-turn latency) or make the pre-check deterministic-first.
- **Determinism for QC** — the two-sided live QC (Gemma) is probabilistic; pair it with a deterministic
  unit test at the chokepoint (turn-intent=write ⇒ catalog excludes adopt; turn-intent=setup ⇒ includes).

## FINALIZED DESIGN (from the 2 architecture maps + the autonomy decision)

**Autonomy decision (PO, 2026-07-19): request-scoped + propose-the-rest.** The co-writer is autonomous for
what DIRECTLY fulfills the turn's request (prose, chapter/scene create, draft save, a named character);
anything ADJACENT or high-impact/bulk becomes a PROPOSED workflow the user approves.

**Root cause (map-confirmed):** all three reach-paths — hot-seed, `find_tools`, `tool_load` — read ONE object
`discovery_catalog`. My prior fixes filtered *inside* hot_tool_names + the find_tools search fns, but
`tool_load_result` (`tool_discovery.py:818`) loads ANY name from the catalog with no filter (not even legacy).
That's the leak. **The one honest chokepoint is the catalog itself.**

**The binding (why control "wasn't good yet"):** the intent signal already exists — `resolve_skills_to_inject_async`
embeds the turn message (once, already paid) and injects `glossary_shaping` (whose description = "set up the
book's world ontology") when the turn is setup-intent (score ≥ 0.35) OR glossary is pinned. Today that gates the
*guidance* (prompt) but NOT the *capability* (the tool stays catalog-reachable). **Bind them: the high-impact
setup tools are in `discovery_catalog` iff `glossary_shaping` is injected this turn.** Guidance and capability
move as one — the exact disconnect the PO flagged.

### Build
- **Slice 1 — capability floor (the fix).** A catalog filter applied at assembly (`stream_service.py:4313`
  fresh + `:5703` resume): if `glossary_shaping` is NOT in the turn's injected skill codes, drop the
  `INTENT_GATED_SETUP_TOOLS` (start: `glossary_adopt_standards`; consider `glossary_list_system_standards`,
  `glossary_propose_kinds`, `glossary_plan`, `glossary_book_sync_apply`, `glossary_propose_batch`) from the
  catalog. Because hot-seed + find_tools + tool_load all iterate this one list, the tool is simultaneously
  un-seeded, un-findable, un-loadable. Reuses the injected-skills result already computed at `:3797-3814`.
  The injected-skills signal is the SAME intent used for the guidance — one signal, both layers.
- **Slice 2 — the proposal (control-model completion).** With the tool structurally unavailable on a write
  turn, the agent CANNOT adopt — it will naturally OFFER. Sharpen the lean glossary core prompt to offer via
  the world-setup **workflow** (`intent_workflows.py` already matches "set up my world" deterministically +
  the S-12 propose→approve loop exists). Only build the explicit workflow-proposal wiring if the two-sided QC
  shows the emergent "offer in prose" isn't enough.

### QC (two-sided — MANDATORY, this is the whole point)
1. **Write turn** ("create Chapter 1 and write the opening") → agent creates the chapter, `adopt_standards`
   NEVER called (unreachable), no unrequested confirm. *(the bug, gone)*
2. **Setup turn** ("set up my world's lore for a fantasy novel") → `glossary_shaping` injects → tools in
   catalog → adopt reachable + works. *(did NOT break legit setup)*
Plus a **deterministic unit test** at the filter: codes without `glossary_shaping` ⇒ catalog excludes the
gated set; codes with it ⇒ includes. (Live Gemma is probabilistic; the unit test is the hard proof of the seam.)

## Plan
brainstorm ✅ → maps ✅ → finalized design ✅ → build Slice 1 at the chokepoint → two-sided QC + unit test →
commit → assess whether Slice 2 (explicit proposal) is needed.
