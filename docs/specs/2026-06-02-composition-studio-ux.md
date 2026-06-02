# Composition Studio — Writer-POV UX & GUI Draft

> **Date:** 2026-06-02 · Companion to [composition-service vision](2026-06-02-composition-service-vision.md) + [prior-art research](../research/2026-06-02-ai-novel-composition-prior-art.md).
> **Why this doc:** design the GUI from the *writer's* point of view first — a concrete UI draft *derives* the backend (which is why the author wants the HTML draft locked before finalizing architecture).
> **Mockup:** [composition-studio-mockup.html](composition-studio-mockup.html) — open in a browser.

---

## §1 The writer's jobs-to-be-done (POV)

What a novelist actually needs when continuing a book *with* AI — ranked by how often it makes writers **abandon** AI tools:

1. **"Never contradict my world."** Continuity breaks (AI forgets a death, revives a lost sword, mis-ages a character) are the #1 reason writers quit AI tools. Non-negotiable.
2. **"Show me what you're using — and let me control it."** Writers distrust black-box generation. They want to *see* the canon the AI grounds on, and pin/exclude it.
3. **"Sound like me / like this character."** Voice consistency across 100k words.
4. **"Don't know the future."** The AI must not leak/foreshadow events from later in the timeline (spoiler-safety).
5. **"Keep my story bible without me maintaining it."** Manual wikis rot; writers want it to fill itself.
6. **"Keep me in flow."** Write → AI continues → I steer, without context-switching to a separate wiki tab.
7. **"Help me when I'm stuck."** Brainstorm, expand a beat, describe a place, offer alternatives.
8. **"Respect my plan, but surprise me within it."** Outline-aware, not mechanically beat-filling (anti-slop).
9. **"I stay the author."** Accept / edit / reject. Assistance, not replacement — the research-confirmed *hybrid* mode is the only one that works today.

---

## §2 Needs → Features → Foundation leverage

| Writer need | Studio feature | Leverages (already built) |
|---|---|---|
| Never contradict canon | **Continuity critic** inline (flags conflicts before accept) + **canon rules** | `loreweave_eval` judge + `canon_rule` (COMP) |
| See/control grounding | **Live Grounding panel**: present characters + state, relevant lore, active rules, timeline-so-far — each pin/excludable | RAG packer (COMP-A6) over `drawers/search`, `timeline`, entity/relations, glossary `select-for-context` |
| Voice consistency | **Voice profiles** per narrator/character | COMP `voice_profile` → prompt assembly |
| No spoilers | **Spoiler-safe cutoff** ("AI sees events ≤ here") | `GET /timeline?before_order=` |
| Auto story bible | Outline + graph **update themselves** as you write | extraction **flywheel** (approved chapter → book-svc → existing extract → graph) |
| Stay in flow | **Inline continue** + streaming co-write in one surface | LLM gateway `POST /v1/llm/stream` (`vercel-ai-ui-v1`) |
| Stuck → unstuck | **Selection tools**: Rewrite · Expand · Describe · Tone | LLM gateway `completion` |
| Stay the author | accept / edit / regenerate; **mode toggle** (Co-write ↔ Auto) | chat feedback+regenerate pattern (shipped) |
| Plan-aware, not mechanical | **Outline navigator** + per-beat goal + structure template | COMP `structure_template` + `outline_node` |
| Track setups/payoffs | **Plot-thread tracker** (open → paid) | COMP `outline_node` + graph relations |

**Every feature maps to something already in production.** The net-new is the studio UI + the packer + the prose-critic dimensions.

---

## §3 GUI comparison with other platforms

| Capability | Sudowrite | Novelcrafter | NovelAI | Campfire / World Anvil / Plottr | **LoreWeave Studio** |
|---|---|---|---|---|---|
| Story bible / codex | Story Bible (manual) | **Codex** (manual wiki + relationships) | Lorebook (manual, key-triggered) | Modular, manual | **Auto-built knowledge GRAPH from the book** |
| Inline AI writing | ✓ Write + tools | ✓ scene editor + chat | ✓ continuation | ✗ (worldbuilding only) | ✓ streaming co-write |
| Grounding transparency | partial | codex "mentions" | key matches | n/a | **Live per-scene panel, author-editable** |
| Continuity / quality gate | ✗ (manual reread) | ✗ | ✗ | ✗ | **Calibrated continuity critic, inline** |
| Canon invariants | ✗ | ✗ | ✗ | ✗ | **Canon rules (declarative)** |
| Spoiler-safe timeline | ✗ | ✗ | ✗ | timeline view (manual) | **Spoiler-cutoff RAG** |
| Diagrams (relationship / timeline / beats) | canvas | plan board | ✗ | ✓ strong (manual) | **Wired to the live graph** |
| Feedback loop | ✗ | ✗ | ✗ | ✗ | **Flywheel: prose → graph → next scene** |
| Hosting / model | SaaS, Muse model | BYOK | SaaS | SaaS | **self-host + BYOK** |

**Positioning in one line:** *Novelcrafter's codex + Sudowrite's writing tools + a continuity judge none of them have + a story-bible that maintains itself.*

The two things **nobody** ships — and we already own the hard half of — are the **continuity critic** (calibrated judge) and the **auto-built graph** (vs hand-maintained wiki). Those are the demo moments.

---

## §4 The Studio layout → architecture (the big picture)

A **3-zone studio** inside the Composition tab of `BookDetailPage` (`/books/:bookId/composition`):

```
┌── Studio toolbar: beat goal · [Co-write|Auto] · Continuity ✓/⚠ · +N facts · Generate ──┐
├───────────────┬─────────────────────────────────────┬──────────────────────────────────┤
│ LEFT          │ CENTER                              │ RIGHT (the differentiator)        │
│ Outline nav   │ Manuscript editor (serif)           │ Tabs: Grounding · Style/Voice ·   │
│ Arc>Ch>Sc>Beat│ • prose + streaming AI continuation │        References · Critic         │
│ Plot threads  │ • continuity-flag underline         │ Grounding = the LIVE RAG context: │
│ [Outline /    │ • selection tools (rewrite/expand)  │  present chars+state · lore cards ·│
│  Relations /  │ • compose bar ("guide the AI…")     │  active canon rules · timeline cut │
│  Timeline]    │                                     │  (each pin / exclude)             │
└───────────────┴─────────────────────────────────────┴──────────────────────────────────┘
```

**Each zone derives a backend piece** — this is how the UI gives the architecture picture:

| UI element | Backend it implies |
|---|---|
| Outline tree + structure badge | COMP `outline_node` + `structure_template` tables |
| Plot-thread tracker | `outline_node` (thread nodes) + graph relations |
| Editor continue / stream | LLM gateway `/v1/llm/stream`; accept → COMP `draft`/`revision` |
| Selection tools | LLM gateway `completion` jobs |
| Continuity underline | `loreweave_eval` prose-critic verdict (new dims) |
| **Grounding panel** | **the RAG packer (COMP-A6)** — `drawers/search` + `timeline?before_order=` + entity/relations + glossary `select-for-context`; pin/exclude = packer budget input |
| Active canon rules | COMP `canon_rule` (feeds packer head **and** critic) |
| Style / Voice / References tabs | COMP `style_profile` / `voice_profile` / `reference_source` → prompt assembly |
| Critic tab (scores) | `loreweave_eval` panel: coherence / voice-match / pacing / canon-consistency |
| Mode toggle Co-write↔Auto | `/stream` (live) vs `completion` job + RabbitMQ callback (batch) |
| "+N facts" flywheel pill | approved chapter → book-svc → existing extraction → graph |
| Relations / Timeline diagram views | reuse `GET /entities`,`/relations`,`/timeline`; edits via `relations/correct`,`PATCH /events` |

---

## §5 Open UX questions (to settle on the draft)

- **U1** — Default right-panel tab: **Grounding** (transparency-first) vs the manuscript-only "zen" mode toggle?
- **U2** — Continuity critic: **block-on-accept** for hard canon-rule violations, or always advisory (warn-only)?
- **U3** — Auto mode surface: generate a **whole chapter** then review, or beat-by-beat with a gate between each?
- **U4** — Diagram views inline (toggle the left rail) vs a full-screen "map" sub-route?
- **U5** — How much of the Grounding panel is **editable in place** (pin/exclude/add-rule) vs read-only with deep-links to Glossary/Knowledge tabs?

---

## §6 Inherited UI patterns (from competitor audit — 2026-06-02)

From [competitor-ui-ux-audit.md](../research/2026-06-02-competitor-ui-ux-audit.md). Three cheap, high-trust patterns folded in **before lock** (shown in [mockup v3](composition-studio-mockup-v3.html) — `#heat` / `#focus`):

1. **Provenance highlighting** (Sudowrite) — AI-written text the author hasn't edited yet is tinted (amber, our theme) + tagged `✦ AI · unreviewed`; clicking/editing clears it. Builds trust; trivial as a TipTap mark.
2. **Focus / typewriter mode** (Ulysses, Dabble) — a Focus toggle hides side panels + dims non-current paragraphs, keeping a **floating continuity pill** reachable (Dabble's mistake = hiding notes entirely in focus).
3. **In-prose mention-linking + heatmap** (NovelCrafter Codex) — entities underlined in prose (reuse the existing glossary highlight); a Grounding **mention heatmap** + "Show heatmap in prose" toggle make *what the AI will get* visible before generating.

Deferred-but-noted: **V1** — beats-with-`[directives]`, filter Scene-Graph by entity, command palette (Power), Linked-Mentions per entity, curated colored relationship web. **V2** — adaptive goals/stats, whole-draft snapshots, export-with-wizard. **Skip** — NovelAI keyed-injection, canvas-as-whole-app.
