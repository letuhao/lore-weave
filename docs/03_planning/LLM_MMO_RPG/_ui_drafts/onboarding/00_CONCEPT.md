# Onboarding — Concept Pass (fundamentals before pixels)

> **Status:** DRAFT 2026-07-29. Concept-level rework of PO_001's UX layer.
> **Does NOT retire** [`features/03_player_onboarding/PO_001_player_onboarding.md`](../../features/03_player_onboarding/PO_001_player_onboarding.md) — that spec's
> domain model, events and cascade stay valid. What this pass reworks is the **UX framing**
> and the **screen spine**.
> **Companion drafts:** [`index.html`](index.html) · sibling game-UI drafts
> [`../CELL_SCENE_v4_layered.html`](../CELL_SCENE_v4_layered.html) · [`../MAP_GUI_v2.html`](../MAP_GUI_v2.html)

---

## §0 — Why this pass exists

The PO_001 wireframe set was authored **2026-04-27**. The track's canonical medium was
corrected **2026-06-20** in [`00_VISION.md` §0](../../00_VISION.md):

> **This is a rendered 2D / 2.5D MMO RPG — NOT a text/chat game.** […] That framing is
> **wrong and dangerous**: it leads a reader to build a SillyTavern-style chat client
> instead of a game client.

The wireframes predate that correction by ~8 weeks, and one of them did not survive it.
[`wireframes/05_first_turn.html`](../../features/03_player_onboarding/wireframes/05_first_turn.html) — the screen the *entire* onboarding
flow terminates into — is a chat client:

```html
<textarea class="input" placeholder="Nhập hành động hoặc lời nói của Lý Minh..." rows="3">
<button class="btn-primary">Gửi turn →</button>
```

Prose narration block · a free-text action box · five verb buttons (Speak / Action /
MetaCommand / FastForward / Narration) · **no canvas, no avatar, no tilemap**. It is
precisely the artifact §0 warns about. Building the onboarding GUI directly from that set
would deliver the player into the wrong game.

**This is why the concept pass comes before the HTML.** The rest of the flow is broadly
salvageable — but only once we say what onboarding actually *is*.

---

## §1 — What onboarding IS

> **Onboarding is the function that turns a person holding an account into an actor
> bound into a world that is already running.**

Its deliverable is not screens. Its deliverable is **one binding**:

```
user ──▶ actor ──▶ cell ──▶ channel
```

Everything else — the mode picker, the wizard, the AI assistant, the portrait — is
*ways of arriving at that binding*. If a design decision does not make the binding more
correct or the arrival more legible, it is decoration.

The binding is not hypothetical. It has a concrete hole waiting for it in shipped code —
[`ChannelRoom.ts:369`](../../../../../services/game-server/src/rooms/ChannelRoom.ts#L369):

```ts
private actorForUser(userId: string): string {
  const raw = process.env.LW_CHANNEL_ACTOR_MAP ?? '';   // dev map via env var
  ...
}
```

with the comment *"V1 resolves this from the PC-substrate binding."* **Onboarding exists to
delete that env var.** That is the feature's completion test, and it is not fakeable.

---

## §2 — The five fundamentals

Everything in the screen spine below is derived from these. If a screen cannot be traced
back to one, it does not belong in V1.

### F1 · The world is already running — you immigrate, you do not "new game"

Realities are authored (`RealityManifest`), cells are simulated by `sim-core` islands, and
clocks are already ticking (`TDIL_001` actor/soul/body clocks). There is no save file to
create. The nearest correct metaphor is **immigration into a live world**, not *New Game →
Character Creation → Chapter 1*.

**Consequence:** the flow must answer *"where and when am I landing, and who is already
there?"* — questions a conventional character creator never asks.

### F2 · The client proposes; it never writes

`CWC-A1` — the room holds no authority. The browser already obeys this for turns
([`channel-client.ts`](../../../../../frontend-game/src/net/channel-client.ts) → `turn.submit` → signed proposal → bus →
commit-service). Character creation is **the same shape**: the GUI emits
`Forge:RegisterPc` / `Forge:BindPcUser` proposals and waits for committed events.

**Consequence:** every creation screen has three outcomes to render, not one —
`resolved` / `discarded` / `rejected` (the closed set in
[`channel-protocol.ts`](../../../../../frontend-game/src/net/channel-protocol.ts)). A "Create" button with only a success path is
already wrong. This is also why V1 chose all-or-nothing submit (Q7): one proposal, one
verdict.

### F3 · Reality is chosen first, and it configures everything after

Per `PO-A6`, onboarding config is **author-declared per reality**: which modes exist,
which canonical PCs are offered, whether the AI assistant is on, where you spawn. Theme,
canon, language and available identities all follow from it.

**Consequence:** the mode picker is **data-driven, not hardcoded**. A screen that always
shows three modes contradicts the manifest. Reality select is not a cosmetic first step —
it is the configuration load.

### F4 · PC and NPC are one substrate; "PC" is a binding, not a type

`actor_core` is universal. Being a player character means an actor carries a `user_id`.

**Consequence — the biggest simplification available here.** The "3 onboarding modes" are
not three features. They are **three entry points into one primitive**:

| Entry point | What actually happens | Primitive |
|---|---|---|
| **A · Canonical** | bind to an actor that already exists in canon | `BindPcUser` **only — no creation at all** |
| **B · Custom** | create a new actor, then bind | `RegisterPc` → `BindPcUser` |
| **C · Xuyên Không** | new *soul* onto an existing *body*, then bind | `RegisterPc(body_memory_init)` → `BindPcUser` |

Mode A is *cheap* in a way the current spec never states — it needs no creation cascade at
all. That makes it the correct first vertical slice, and it makes the 14-feature cascade a
Mode-B/C concern rather than a prerequisite for shipping anything.

### F5 · The terminal state is a rendered cell, not a prose box

Per `00_VISION §0` + `ILR-A2` three-layer position stack: arrival means **an avatar
standing in a cell on a tilemap**, with other actors visible, in near-realtime.

**Consequence:** the last onboarding screen hands off to the cell scene
([`CELL_SCENE_v4_layered.html`](../CELL_SCENE_v4_layered.html) / `frontend-game` `/play`). LLM narration is a
**panel inside that client**, never the client itself.

---

## §3 — The correction F5 forces: "First Turn" is a category error

This is the deepest finding of the pass, and it is not merely cosmetic.

The game is a **hybrid**: near-realtime avatar movement (`RTM-A1..A9`) + turn-based
combat/interaction (`TG-A1..A4`, instanced dedicated combat scene). Turns are a **mode you
enter**, not the base interaction.

`05_first_turn.html` makes turn-submission the ground state of existence — you arrive and
your only affordance is to compose a turn into a textarea. Under the corrected medium, a
newly-arrived player's actual first affordance is to **move**, look around, and see other
actors. A turn begins when something engages them.

**So the screen is renamed and rebuilt: `Arrival`, not `First Turn`.**

| | Old `05_first_turn` | New `Arrival` |
|---|---|---|
| Ground state | compose a turn | stand in a cell, free movement |
| Primary surface | prose narration block | rendered cell (iso canvas) |
| Input | textarea + "Gửi turn →" | movement; interaction on approach |
| Narration | *is* the game | a dockable sub-layer panel |
| Turn UI (SR11 state machine) | always on | appears **when a turn opens** |

The SR11 turn state machine is not discarded — it is **scoped**. It was correct; it was
merely promoted to the whole interface by the stale framing.

---

## §4 — Screen spine that follows

Four screens. Each traces to a fundamental. Nothing else is V1.

| # | Screen | Fundamental | The one question it answers |
|---|---|---|---|
| 00 | **Account** | — | Are you you? *(auth-service already ships this — cheapest screen)* |
| 01 | **Reality** | F3 | Which world, and what does it allow? |
| 02 | **Entry** | F4 | How do you acquire an actor? *(offered set comes from the manifest)* |
| 03 | **Arrival** | F1 · F2 · F5 | Landed: where, when, who is here? |

Mode B's 8-step wizard and the ~46-field Advanced grid sit **inside** step 02 as depth, not
as separate spine screens. They are medium-neutral (a form is a form), so the existing
[`03b_custom_pc.html`](../../features/03_player_onboarding/wireframes/03b_custom_pc.html) and
[`03b2_advanced.html`](../../features/03_player_onboarding/wireframes/03b2_advanced.html) drafts remain usable as-is and are
deliberately **not** redrawn here.

---

## §5 — Audit of the 2026-04-27 set

| Screen | Verdict | Reason |
|---|---|---|
| `00_landing` | ✅ **Keep** | Medium-neutral; auth-service backs it today |
| `01_reality_select` | ⚠️ **Rework** | Right idea; must become data-driven (F3) and show the world, not text cards |
| `02_path_choice` | ⚠️ **Reframe** | Keep the screen, restate as 3 entry points to one binding (F4) |
| `03a_canonical_pc` | ✅ **Keep** | Forms are medium-neutral |
| `03b_custom_pc` | ✅ **Keep** | ″ |
| `03b2_advanced` | ✅ **Keep** (scope-flag) | ″ — but 46 fields at V1 is a UX-load question, not a medium one |
| `03c_xuyen_khong` | ✅ **Keep** | ″ — the differentiator |
| `04_confirm` | ⚠️ **Rework** | Preview must show the **cell you land in**, not a prose opening; must render the 3-verdict outcome (F2) |
| `06_ai_assistant` | ✅ **Keep** | A field-filler; medium-independent |
| `05_first_turn` | ❌ **Rebuild** | Chat client — contradicts `00_VISION §0` (§3 above) |

**8 of 10 survive.** The design work of 2026-04-27 was not wasted; it was aimed at a
medium that has since been corrected, and exactly one screen sat on the fault line — the
terminal one.

---

## §6 — Questions the fundamentals raise (open)

These are consequences of F1–F5 that the 2026-04-27 pass could not have asked, because
under a chat medium they do not exist.

| # | Question | Why it is now load-bearing |
|---|---|---|
| **C-Q1** | **Where does the avatar sprite come from?** | A rendered client must draw the PC. The audit treats appearance as *text fields*, and portraits are deferred to V2+ (`PO-D8`) — but a **sprite is not a portrait**, and it is mandatory at V1. Believed to be a genuine gap in the current design. |
| **C-Q2** | Is spawn-cell chosen on a **map** or in a dropdown? | F5 + `MAP_GUI_v2` exist. A dropdown of cell names in a spatial game is a text-medium leftover. |
| **C-Q3** | Does onboarding run **outside** the game client (React routes) or **inside** it (an in-world arrival scene)? | F1 says the world is already running. An in-world arrival is more truthful and costs more. V1 likely picks routes — but say so deliberately. |
| **C-Q4** | What does Reality Select **show**? | Text cards (current) vs. the world map. F3 makes this the config load; F5 argues it should look like a world. |
| **C-Q5** | Which of the ~46 fields survive first contact? | Not a medium question — a UX-load one. 46 fields before a player has seen the world is a funnel risk that no wireframe tests. |

**None of these blocks the drafts below.** They are what the drafts are *for* — to make the
questions concrete enough to answer.

---

## §7 — What this implies for build order

F4 changes the sequencing. Because **Mode A needs no creation cascade**, the first vertical
slice is far smaller than PO_001's 14-feature cascade suggests:

```
account (auth-service — ships today)
  → reality select (1 reality, hardcoded manifest)
    → entry point A only (bind to a canonical actor)
      → BindPcUser proposal → committed event
        → arrival in a rendered cell
          → LW_CHANNEL_ACTOR_MAP deleted   ◀── the completion test
```

Modes B and C, the 8-step wizard, the 46-field grid and the AI assistant all build **on
top of that same binding**, and none of them are needed to prove it.
