# Competitor UI/UX Audit — for locking the Composition UI

> **Date:** 2026-06-02 · Companion to [composition-studio-ux.md](../specs/2026-06-02-composition-studio-ux.md) + mockup v3 + the what-if/branch mock.
> **Question:** what UI/UX do rivals (traditional writing tools + AI assistants) have, where are we strong/weak, and **what should we inherit before locking the UI?**
> **Method:** two parallel research sweeps (interface/interaction focus, source-cited). This doc keeps the decision-useful synthesis; per-tool detail is condensed below.

---

## §0 Bottom line

**No established tool fuses {minimal focus-writing + visual scene planning + an *auto* knowledge graph + continuity *checking*}.** That intersection is our white space — confirmed independently by both sweeps. We are well-positioned, and most "gaps" are *polish patterns* to inherit, not missing pillars.

**Three strategic openings nobody has closed — our moats:**
1. **Compare AI takes *as branches*.** Only Sudowrite has true parallel-compare (History cards), and it's disjoint from structure. Nobody ties multi-take comparison to a branching/what-if structure → our Scene-Graph + what-if owns this.
2. **Post-hoc consistency *checking*.** Almost everyone only *injects* canon and hopes; only LivingWriter "AI Analysis" audits output, and it's buried. Our **continuity critic** is a rare differentiator — surface it as an inline linter, not a report.
3. **Plan/draft live-sync.** The #1 recurring competitor failure (Sudowrite Canvas, LivingWriter Boards, Squibler) is a **manual copy-paste** between board and prose. Our canvas + editor share **one live `scene_node` model** → no export step.

Plus two validated decisions: **Casual/Power** (≈ Squibler Auto/Guided; progressive disclosure is the universal antidote to the #1 UX failure = overwhelm), and **server-SSOT** (Raptor's browser-only data-loss is a failure we market against).

---

## §1 The landscape (condensed)

**Traditional tools cluster in 3 camps:**

| Camp | Tools | Signature UI | Loved for | Hated for |
|---|---|---|---|---|
| Prose-focus minimalists | **Ulysses · Dabble · Atticus** | 3-column, fade-away chrome, typewriter mode | distraction-free flow, goals, export (Atticus) | no/!visual planning; Atticus thin |
| Visual planners | **Scrivener · Final Draft · Plottr · Milanote** | corkboard / beat board / timeline lanes / infinite canvas | spatial non-linear planning; cards reorder the manuscript | learning curve; Scrivener Compile "complicated"; Plottr has no editor |
| Worldbuilding wikis | **World Anvil · Campfire · Notion · Obsidian** | typed articles / modular panels / relational DBs / backlinks+graph | deep canon; relationship webs; Obsidian backlinks "build the web for you" | **overwhelm / blank-slate churn** ("most abandon Obsidian within a week") |

**AI assistants:**

| Tool | Layout | Knowledge UI | AI interaction | Multi-take compare? |
|---|---|---|---|---|
| **Sudowrite** | editor + History cards + separate **Canvas** | Story Bible (authored, inline) | Write/**Rewrite/Describe/Expand** on selection; **purple-provenance** insert | **Yes** — 1–6 cards, unstacked side-by-side, star/insert (only one who does) |
| **NovelCrafter** | true 3-pane + Chat | **Codex: auto-mention-linking + heatmap** (best canon *visibility*) | **beats→prose**, inline `[directives]`, @-context chat | No — serial re-roll |
| **NovelAI** | editor + knobs | **Lorebook: keyed injection** (max control/friction) | inline continuation + samplers | No |
| **Storyflow** | **canvas-as-whole-app** | the board *is* the base (opaque) | board-aware chat, @-mention | No |
| **Squibler** | 3-zone + corkboard | Smart Elements (authored) | **Auto/Guided** toggle (≈ our Casual/Power) | No |
| **LivingWriter** | fade editor + 4 Boards | Element cards | **AI Analysis** = rare *consistency check* | No |
| **Raptor** | minimal + folder tree | thin | editable prompts + prompt library; version snapshots | No (post-hoc version compare) |
| **ChatGPT/Claude** | chat (Artifacts/Canvas) | none (paste a bible) | conversational; "3 versions" stacked in one reply | No; **"digital amnesia"** at novel length |

---

## §2 What we already do well (validated — don't second-guess)

- **Auto knowledge graph** — *everyone else is authored* (NovelAI keys / NovelCrafter auto-*links authored entries* / Sudowrite Story Bible). NovelCrafter Codex is the closest and still requires manual entry curation. Our auto-extraction is the differentiator.
- **Continuity critic** — see §0.2. Near-unique.
- **What-if branching + judge** — see §0.1. Novel.
- **Casual/Power + progressive disclosure** — the antidote to the field's #1 failure.
- **Shared live model** — fixes the field's #1 structural failure (plan/draft disconnect).

---

## §3 Gap analysis — what to inherit before locking (the centerpiece)

| Gap (we lack / under-spec) | Who nails it | Verdict | Lands in |
|---|---|---|---|
| **Provenance highlighting** — AI-written-unreviewed text visibly marked until you edit it | Sudowrite (purple) | **INHERIT NOW** (cheap in TipTap, high trust) | Co-writer / editor mark |
| **Focus / typewriter mode** — auto-hide chrome after typing, center current line | Ulysses, Dabble, LivingWriter | **INHERIT NOW** (fits "minimal") — *but keep continuity hints reachable* (Dabble's mistake = hiding notes in focus) | Casual editor |
| **In-prose mention-linking + "what the AI will get" preview / heatmap** | NovelCrafter Codex | **INHERIT NOW** — reuse the existing glossary highlight; show grounding *before* generating | Grounding panel + editor decoration |
| **Beats-as-objects + inline `[directives]`** — terse beat → prose, regenerable per unit | NovelCrafter | **INHERIT V1** | Co-writer + Outline |
| **Filter Scene-Graph/Timeline by entity** ("where does X appear") | Plottr | **INHERIT V1** (strong critic synergy) | Scene Graph + Timeline |
| **Templates/wizards + seeded first-run** (no blank slate) | Plottr, Notion | **INHERIT V1** — graph already seeds canon; add structure starters | onboarding + Beat Sheet |
| **Command palette + rich shortcuts** | Obsidian-class (no *traditional* tool has one) | **INHERIT SOON** (Power differentiator) | Power mode |
| **Backlinks / "Linked Mentions" per entity** | Obsidian, NovelCrafter | **INHERIT SOON** | Cast & Codex |
| **Curated relationship web (colored alliance/rivalry edges)** | Campfire | **INHERIT SOON** — a *designed* view reads better than a raw force-graph | Relationship Map |
| **Adaptive goals + stats/streaks** (quota rebalances on miss) | Dabble, Ulysses 13 | **V2** (was "Later") — the *adaptive* version is rare | Progress & Stats |
| **Whole-draft snapshots, searchable** | Scrivener | **V2** — pairs with what-if (a branch ≈ a named snapshot) | Versions |
| **Compile/export + live multi-format preview** (EPUB/PDF/DOCX) | Atticus | **V2** — real gap for "finish a book"; **ship a wizard, NOT Scrivener's option-dump** | new "Publish" surface |
| **Moodboard / visual inspiration** (char art, mood) | Milanote, Campfire | **LATER/opt** — reuse image-gen-service | optional module |
| Engineer-grade keyed injection / token-budget knobs | NovelAI | **SKIP** — auto-graph hides it; expose tuning Power-only | — |
| Canvas-as-the-whole-app | Storyflow | **SKIP** — editor stays home (already decided) | — |

---

## §4 Pitfalls to avoid (from the research, with the culprit)

1. **Plan/draft disconnect** (Sudowrite Canvas, LivingWriter, Squibler) → our canvas + editor MUST share one live model, no export step.
2. **Opaque grounding** ("AI reads everything" — Storyflow, Sudowrite Story Bible) → make injection **inspectable** (our Grounding panel; add the heatmap).
3. **History/card-list noise** (Sudowrite) → branches/takes need a **lifecycle** (promote / collapse / prune), not infinite scroll. *(Our what-if has promote/discard — extend to takes.)*
4. **Everything-at-once overwhelm** (World Anvil, Campfire, Scrivener Compile, over-built Notion/Obsidian) → Casual genuinely sparse; density behind Power.
5. **Engineer-grade canon controls** (NovelAI) → writer-hostile; hide behind the auto-graph.
6. **Fragmented AI commands** (LivingWriter's 5 separate AI menu items) → one inline co-write loop + side panels beats a command grab-bag.
7. **Serial-only iteration / re-roll-in-place** (everyone but Sudowrite) → hides discarded alternatives; parallel + branch-able is the edge.
8. **Buried review tools** (LivingWriter Analysis) → surface the critic **inline** (a continuity linter), not a report nobody opens.
9. **No persistence / local-only** (Raptor browser data-loss) → covered by server-SSOT.

> **Verification caveat:** the claim that Sudowrite Canvas "AI reads card *proximity/spatial layout*" is **not confirmed** by primary docs (they describe Canvas gen as referencing the Story Bible). If we ever make canvas layout inform the AI, it'd be something competitors *market* but don't appear to *ship* — a genuine differentiator, not a solved pattern.

---

## §5 Sources (key)

**Traditional:** Scrivener ([L&L corkboard](https://www.literatureandlatte.com/blog/organize-your-scrivener-project-with-the-corkboard), [Compile redesign](https://www.literatureandlatte.com/blog/scrivener-3-redesigning-compile)), Final Draft ([Beat Board](https://www.finaldraft.com/blog/how-to-use-final-draft-the-beat-board)), Ulysses ([Goals](https://help.ulysses.app/goals), [Dashboard](https://help.ulysses.app/en_US/the-dashboard/dashboard)), Plottr ([Timeline](https://docs.plottr.com/article/54-timeline-overview)), World Anvil ([Kindlepreneur](https://kindlepreneur.com/world-anvil/)), Campfire ([Reedsy](https://blog.reedsy.com/guide/book-writing-software/campfire-write-review/)), Obsidian ([Canvas](https://obsidian.md/canvas), [learning curve](https://www.xda-developers.com/obsidian-learning-curve/)), Notion ([story bible](https://www.notion.com/templates/story-bible)), Dabble ([Plot Grid](https://help.dabblewriter.com/en/articles/2692382-exploring-dabble-s-plot-grid)), Atticus ([Reedsy](https://reedsy.com/studio/resources/atticus-review)), Milanote ([for writers](https://www.themanuscripteditor.com/post/meet-milanote-the-digital-workspace-for-writers-and-creatives)).
**AI:** Sudowrite ([Write](https://docs.sudowrite.com/using-sudowrite/1ow1qkGqof9rtcyGnrWUBS/write/pvxUvbQqYybfEosqx1sXjY), [Muse](https://docs.sudowrite.com/using-sudowrite/1ow1qkGqof9rtcyGnrWUBS/sudowrite-muse/4k9bFDMSyic6mFPkYFHrkZ)), NovelCrafter ([Codex](https://www.novelcrafter.com/features/codex), [beats](https://docs.novelcrafter.com/en/articles/8675715-crafting-beats)), NovelAI ([Lorebook](https://docs.novelai.net/en/text/lorebook/)), Storyflow ([site](https://storyflow.so/)), Squibler ([Reedsy](https://reedsy.com/studio/resources/squibler-review)), LivingWriter ([automateed](https://www.automateed.com/livingwriter)), Raptor ([review](https://wordsatscale.com/raptorwrite-review/)), ChatGPT/Claude novel-length ([guide](https://www.glbgpt.com/hub/how-to-use-chatgpt-to-write-a-full-novel-the-2026-engineering-guide/)).
