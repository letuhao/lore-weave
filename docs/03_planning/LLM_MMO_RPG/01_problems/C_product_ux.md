<!-- CHUNK-META
source: 01_OPEN_PROBLEMS.ARCHIVED.md
chunk: C_product_ux.md
byte_range: 14106-20077
sha256: fb5b4ba200df785e528dd0fab152291aeb885eb5ce721fa600bb9760bd180194
generated_by: scripts/chunk_doc.py
-->

## C. Product / UX

### C1. Player voice vs narrative voice — **PARTIAL**

**Problem:** User types `/say I hate the king`. Does the AI narrator rewrite this as "You stand and declare, voice trembling with rage, that you despise the king"? Or keep it raw?

**Why hard:** Rewrite = novelistic feel but player loses their voice; raw = chat-bot feel, breaks immersion.

**Resolved by:** 3-mode voice framework with inline override:

- **C1-D1** — 3 modes: **terse** (literal, minimal wrap), **novel** (full prose rewrite), **mixed** (auto-adapt: pivotal=novel, casual=terse). **V1 default = mixed.**
- **C1-D2** — inline per-turn override: `/verbatim` forces terse, `/prose` forces novel for current turn only.
- **C1-D3** — World-Rule override (DF4): author can force a mode per reality (e.g., literary canon → novel locked).
- **C1-D4** — persistence: user voice preference per book stored in auth-service user-preferences.
- **C1-D5** — LLM Safety Layer integration: voice mode is a prompt-template variable; output filter (A6-D4) enforces mode-consistency (terse must not produce 3-paragraph rewrite).

Decisions C1-D1..D5 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN`:**
- "Mixed" auto-adapt classifier (pivotal vs casual) — V1 tuning
- Which mode users prefer at scale — V1/V2 analytics
- Mode-specific prompt template quality — V1 copy refinement per `UI_COPY_STYLEGUIDE.md`

### C2. Narrative pacing — **ACCEPTED (research frontier)**

**Problem:** Unstructured LLM small-talk devolves into infinite low-stakes conversation. Real stories have beats, rising tension, payoff. LLMs alone don't do this.

**Why hard:** Requires an "AI GM" layer above NPCs that tracks narrative tension and injects events/complications. Open research (closely linked to F2).

**Accepted stance (2026-04-23):** A proper AI-driven narrative pacing layer is open research. **V1 pragmatic workaround**: author-authored quest scaffolds (F3-D1/D2) provide structural pacing — beats, rising action, outcomes — at scene level. Narrator fills in prose within those beats but does NOT drive tension at story level. Small-talk is allowed to drift; players self-regulate or close session.

**Revisit trigger:** V2+ prototype data on session-length drift rates + public research progress (Generative Agents successors, multi-agent narrative planners). If small-talk sessions empirically feel "dead" and F3 scaffolds can't be authored fast enough to cover it, reopen with concrete V1 data.

**Residual — no longer blocks design:** pacing is a product-quality concern, not a structural blocker. V1 can ship without it.

**Notes:** Generative Agents paper (Park et al.) used "reflection" + "planning" but didn't solve pacing for a human audience. Could cheat with scripted quest scaffolds and let LLM fill in, like tabletop modules.

### C3. Cold-start empty-world problem — **PARTIAL**

**Problem:** An MMO is no fun with 0 other players. Day 1 of launch: no one logs in twice.

**Why hard:** Product/marketing, not technical. Solution space includes: solo-first (Shape A) onboarding that doesn't feel empty; AI "populated" NPCs that substitute for players; scheduled "events" that pull people back.

**Resolved by:** Product strategy that reframes the problem — C3 is largely dissolved by earlier decisions (multiverse NPCs as world-fillers, M1 discovery defaults, staged V1/V2/V3 scoping). Explicit locks:

- **C3-D1** V1 = **solo-first MVP**. Single-player RP is the first shipping experience. MMO population is NOT a V1 requirement.
- **C3-D2** NPC-populated world is the primary immersion mechanism (LLM-driven NPCs, not other players). Matches multiverse §1 philosophy. MMO is additive, not foundational.
- **C3-D3** Staged launch funnel: Reader (M7-D2) → single-player → discover other timelines (M1-D1) → (V2) coop scenes → (V3) MMO persistence. Each step self-sufficient.
- **C3-D4** Scheduled events (V2+) create predictable synchronous play windows without always-on population. Full UX spec deferred to DF5.
- **C3-D5** Friend-follow (reuses M1-D3) = primary organic MMO concentration mechanic.
- **C3-D6** Anti-dispersion defaults (reuses M1-D2 composite ranking + M1-D6 create-new gating) prevent fork-spam creating lonely realities at launch.

Decisions C3-D1..D6 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN`:**
- Scheduled-event UX spec (DF5 detail)
- Launch marketing strategy (product/growth scope, not design-doc scope)
- First-week funnel metric targets — V1 prototype data

### C4. Author canon vs player-emergent narrative — **PARTIAL**

**Problem (original):** A book's author has a canonical story. Players in the world create emergent stories. How do these relate? Is player narrative throwaway, or can it feed back into canon?

**Resolved by:** Four-layer canon model in [03 §3](03_MULTIVERSE_MODEL.md). Author canon lives at L1 (axiomatic) and L2 (seeded). Emergent narrative lives at L3 (reality-local, immutable within its reality). Player stories are **not throwaway** — they are permanent L3 canon of their reality. **Canonization** (L3 → L2 promotion) is an explicit author-gated flow.

**Residual `OPEN`:** IP ownership of canonized content (E3), UI/diff tooling for author review, bright lines for what kinds of L3 events are canonization-eligible.

### C5. Multi-stream UI — **PARTIAL**

**Problem:** User sees simultaneously: other players' chat, NPC narrative responses (slow, streaming), system action results (fast), world event broadcasts. One chat window is too noisy.

**Known approaches:**
- Tabbed streams (say / narration / system / whisper)
- Inline with visual differentiation (color, icon, font)
- Classic MUD pattern: everything in one scrolling log with prefixes

**Notes:** Mostly a UI design problem. Solvable but important to prototype early.

---

