# Research — Narrative Control Formalisms (the "blueprint vocabulary" for guiding an LLM author)

> **Date:** 2026-06-26 · **For:** the planned **narrative motif/pattern library** (composition-service), spec [`docs/specs/2026-06-26-narrative-motif-library.md`](../specs/2026-06-26-narrative-motif-library.md).
> **Framing (locked by PO):** LoreWeave is a *creation system*, not a writing product. The features we build are a **control / blueprint layer**; the LLM is only the **final implementer**. The question is therefore NOT "what prompt makes a model write well" but **"what formal vocabulary can we store as data and exploit with software to constrain the model so any LLM — even a weak self-host — produces structurally sound output."**
> **Method:** targeted web sweep across narratology, computational narrative, and the web-novel craft corpus, plus the closest real implementations. Snippet-level unless a source was fetched (oh-story repo + the 200-constraint paper were fetched).
> **Relationship to prior art:** the earlier [`2026-06-02-ai-novel-composition-prior-art.md`](2026-06-02-ai-novel-composition-prior-art.md) surveyed *products & systems*. This doc surveys the *formal vocabularies* those systems encode — the layer LoreWeave's prior-art doc named as still-missing: "the generation layer + **template library**".

---

## §0 Bottom line

1. **The control-layer thesis is empirically backed, not just intuition.** "Style over Story" (arXiv:2510.02025) measured that when an LLM is free to choose its own authorial constraints, it favors **Style 1.67× over Event/plot**. Uninstructed models under-invest in plot mechanics and over-invest in surface prose — *exactly* the "plan is bland" failure observed with the weak self-host planner. A control layer that **forces Event/plot structure** is the mechanism that inverts this bias. This is the single strongest argument for the whole feature.

2. **Literature already supplies a rich, layered vocabulary** — Propp's 31 functions, Greimas' 6 actantial roles, Polti's 36 situations, the Thompson Motif-Index (a real hierarchical taxonomy), ATU tale-types, plot units / plot graphs, and genre-specific formula packs (web-novel 黄金三章 / 爽点 / 打脸). These map onto **distinct altitudes** (story-form → roles → event-sequence → motif-catalog → genre-formula → fine constraint). LoreWeave already has the **top** (structure templates) and **bottom** (canon rules, style/voice profiles, tension); the **middle — reusable event-sequences and genre packs — is the gap.**

3. **The idea is already implemented in the wild as a skill pack** (`oh-story-claudecode`): a `扫榜 → 拆文 (deconstruct) → 写作 → 去AI味 → review` pipeline whose deconstruction step extracts exactly the reusable units we want (hook techniques, emotion-arc modules, genre formulas, plot-point emotion curves, foreshadow ledgers). It proves the shape ships — but it stores everything as **flat per-project Markdown**, hardcoded and un-queryable. **LoreWeave's edge is to make this a queryable, multi-tenant, self-enriching data architecture instead of files.**

4. **The two formalism families serve different jobs.** The classical ones (Propp/Greimas/Polti/Thompson) are **abstract and dated** → excellent as a **schema/ontology backbone** (function slots, role types, taxonomy IDs), weak as direct generation prompts. The web-novel formulas (套路/爽点/打脸) are **concrete and operational** → ship-ready as generation guidance, but **genre-locked**. The design must encode **both**: a generic motif *schema* (Propp-function-like slots + pre/post-conditions) whose *instances* are genre packs.

5. **Honest boundary (carried from prior art + reconfirmed):** structural grounding helps **plot/action coherence, not interiority/prose** (the KG user-study, arXiv:2505.24803). And the web-novel community itself debates whether rigid formulas (黄金三章) over-constrain. → The blueprint should **constrain Event/plot hard, leave prose/voice freer** — which is precisely the inversion §0.1 calls for, and the anti-slop judge stays the backstop.

---

## §1 The control thesis — why an uninstructed LLM underperforms (the data)

**"Style over Story: Measuring LLM Narrative Preferences via Structured Selection"** (Jung et al., [arXiv:2510.02025](https://arxiv.org/abs/2510.02025)) built a library of **200 theory-grounded narrative constraints** — 50 each across **Event / Style / Character / Setting**, each element split into 5 categories × 10 constraints, normalized to 15–20 words with parallel grammar to remove surface bias. Models were asked to *select* the 20 constraints they found most useful (a process-level probe of preference, no full generation).

**Findings that matter for us:**
- Models selected **Style 1.67× more than Event** (the baseline), Character 1.10×, Setting ≈ Event. Within Style, **Tone & Mood** was favored +88%.
- GPT-4.1 was a "style-dominant outlier" (style +64% vs Gemini); models differ as *authors with distinct preferences*, not interchangeable generators.
- A "Creativity" persona **down-weighted plot and character** further.

**Read-through:** left to itself, an LLM gravitates to voice/tone and neglects plot dynamics and event structure. A weak model does this *worse*. Therefore the highest-leverage control surface is **Event/plot** — which is exactly the motif layer. The 200-constraint taxonomy is also directly reusable as our **fine-grained constraint tag vocabulary** (see §6 mapping).

Corroborating craft signal: the LLM-Chinese-literature homogeneity study ([arXiv:2603.14430](https://arxiv.org/html/2603.14430v1)) finds genre-specific **homogeneity/convergence** in LLM-written Chinese fiction — models collapse to the genre mean without strong steering. Same conclusion: structure must be *imposed*, not hoped for.

---

## §2 The formalism stack — a vocabulary menu, by altitude

The formalisms sort cleanly into altitudes. This ordering is the spine of the data model (each altitude = a layer the planner consumes top-down).

### §2.1 Story-form / arc (macro) — *LoreWeave HAS this*
- **Three-act**, **Hero's Journey** (Campbell/Vogler 12 stages), **Save the Cat** (Snyder, 15 beats), **Story Circle** (Harmon, 8), **Kishōtenketsu** (4), **Dramatica** (the most elaborate: a "storyform" of ~75 structural appreciations from four throughlines).
- **Form:** an ordered list of abstract *beats*, each a slot with a *purpose*. Content-free — says *when* a turn happens, not *what*.
- **In LoreWeave:** `structure_template.beats[] = {key,label,purpose,order}`, 6 built-ins seeded (Save the Cat, Hero's Journey, Story Circle, Kishōtenketsu, Web Novel Arc, Three-Act). ✅ Exists. This is the *ceiling* the motif layer hangs under.

### §2.2 Role / relational structure — *partial*
- **Greimas actantial model** (1966): every narrative action reduces to **6 actant roles** — Subject, Object, Sender, Receiver, Helper, Opponent — on 3 axes (desire, power, transmission). A compact, language-agnostic role grammar.
- **Propp's dramatis personae**: 7 character roles (hero, villain, donor, helper, dispatcher, princess, false hero).
- **Form:** a typed role-binding over the cast — *who fills which function in this unit*.
- **In LoreWeave:** glossary entities + relations exist, but there is **no formal role-binding** a motif could require ("this motif needs a Donor and an Opponent"). → motif schema should carry **role slots** bindable to glossary entities.

### §2.3 Event-sequence / function chain (meso) — **THE GAP**
This is the altitude the user described ("rớt vực → bí kíp → đột phá → báo thù"). Multiple independent traditions formalize it:
- **Propp's 31 functions** ([overview](https://www.researchgate.net/publication/319293980)): the canonical proof that diverse tales share a small set of ordered *functions* (Absentation, Interdiction, Violation, Villainy, Departure, Donor-test, Receipt-of-agent, Struggle, Victory, Return, Pursuit, Recognition…). Functions are **stable units; characters/props vary**. Explicitly described as "a blue-print for a story generation system." This is the closest classical analog to a **motif type**.
- **Polti's 36 Dramatic Situations** (1895): 36 recurring conflict configurations (Revolt, Vengeance, Pursuit, Disaster, Recovery-of-lost-one…), distilled from ~1,200 works — a **conflict-type vocabulary** orthogonal to Propp's sequence.
- **Lehnert plot units** (1981): affect-state units (gains/losses/problems) whose **overlaps form a plot graph** — an early computational encoding of "emotional cause-effect," and a precedent for tension/emotion as a structural signal.
- **Plot graphs** (Scheherazade — Riedl/Li; MEXICA — Pérez y Pérez): events as graph vertices, **sequentiality + pre/post-conditions** as edges; stories generated by walking the graph. MEXICA pieces a story from **plot fragments constrained by pre/post-conditions** — *the* model for "select motif + bind."
- **Story Intention Graphs** (Elson): semantic encoding used to **detect story analogies** — relevant to mining/dedup of motifs.

**Read-through:** the meso layer is well-formalized as **(ordered functional units) + (pre/post-conditions) + (a graph of legal successions)**. That is the motif schema, almost verbatim.

### §2.4 Motif / trope catalog (indexed reusable units) — *only as a flat label today*
- **Thompson Motif-Index of Folk-Literature**: **26 top classes** (A Mythological … Z Miscellaneous), each an alphanumeric **hierarchical ID** (e.g. `B` Animals → `B11` Dragon). Modeled computationally as an **OWL subclass hierarchy** with terminal nodes as Motif instances — i.e. a *real, machine-usable taxonomy of motifs*.
- **Aarne–Thompson–Uther (ATU)** tale-type index: **7 broad categories**, each tale-type entry listing the **motifs that compose it** (cross-referenced to the Motif-Index). This is precisely "**a pattern = a named composition of smaller motifs**" — the composition relation we need.
- **TV Tropes**: the crowd-sourced, modern, exhaustive analog — tens of thousands of tropes linked to works (community-curated, not auto-mined).
- **In LoreWeave:** glossary has `entity_kind='trope'` but only as a *classification label*, with no sequence, composition, or ID hierarchy. → motif library should adopt **hierarchical motif IDs/categories + a "composed-of" relation** (ATU-style).

### §2.5 Genre formula packs (operational, ship-ready) — *missing*
The web-novel craft corpus is the most *operational* layer — concrete enough to generate from directly:
- **黄金三章 (Golden Three Chapters)**: ch1 throws the core conflict; ch2 sustains an **information gap** ("reader knows, antagonist struts" — 信息差) to build 追更欲 (binge-pull); ch3 plants a **long-term anchor** (where the MC is headed) + a long suspense hook. Modern evolution: **"黄金300字 + 黄金30章"** (the hook window is larger now).
- **爽点 / 爽文 (shuǎng-points / dopamine fiction)**: stories engineered around timed **gratification beats**; the unit of design is the emotional payoff.
- **打脸 (face-slap) formula**: arrogant party mocks MC → MC reveals hidden power/identity/backing → humiliation reversal. A **fully specified mini-motif** with roles + ordered beats + emotional target.
- **Cultivation/xianxia tropes**: "trash-turned-genius," fortuitous-encounter (奇遇), hidden-bloodline, closed-door breakthrough, revenge — the exact chains the PO writes ([50 cultivation tropes](https://xiuxian0.com/web-novels/cultivation-novel-tropes/)).
- **Read-through:** these are **motif instances**, not a new schema — concrete, role-bearing, emotion-targeted, genre-locked. They are the ideal **seed pack** for a tu-tiên / báo-thù library and the validation that the schema must carry: roles, ordered beats, an emotion/tension target, and genre tags.

### §2.6 Fine constraint tags (per-scene) — *partial*
- The **200-constraint library** (§1) is the vocabulary here: Event / Style / Character / Setting tags applied per scene.
- **In LoreWeave:** `canon_rule`, `style_profile` (density/pace), `voice_profile` (per-character tags), `tension` (1–5) already cover slices of this. → the motif's "fine tags" can reuse these surfaces rather than invent new ones.

---

## §3 Closest real implementations (the bar to clear)

### §3.1 `oh-story-claudecode` — the user's idea, shipped as files
A Claude Code skill pack for web-novel writing ([github](https://github.com/worldwonderer/oh-story-claudecode)). Pipeline: **`/story-setup` → `/story-…-scan` (market) → `/story-…-analyze` (拆文 / deconstruct) → `/story-…-write` → `/story-deslop` → `/story-review`**. The deconstruction step extracts (concrete artifacts we can mirror as schema):

| Artifact | What it is | LoreWeave analog |
|---|---|---|
| `钩子技法` — **13 chapter-ending hook types** | reusable cliff-hanger catalog | motif sub-kind = `hook` |
| `情绪设计` — **6 emotion-arc templates** | reusable emotional modules | motif sub-kind = `emotion_arc` |
| `21大题材写作公式` — **21 genre formulas** | genre packs | motif `genre` packs (§2.5) |
| `情节节点` w/ **emotion marker −9…+9** | plot points on an emotion curve | maps to `tension` + an emotion signal |
| `伏笔.md` — foreshadow w/ **status tracking** | promise/payoff ledger | `narrative_thread` (✅ exists) |
| `文风.md` / `节奏.md` | style + pacing, separated | `style_profile` (✅ exists) |
| `角色/{name}.md` + `动机链` (motivation chains) | per-character voice + motive | `voice_profile` + glossary |

**Critique:** everything is flat per-project Markdown under `拆文库/{title}/` and `对标/{书名}/` — **hardcoded, single-project, not queryable, no cross-work reuse, no tenancy, no semantic retrieval.** This is the exact thing the PO ruled out ("không hardcode như cái bạn search"). LoreWeave's job is to lift this into a **data architecture** (Postgres SSOT + embeddings + optional Neo4j graph) with **book/user/system tiers** and a **mining flywheel**.

### §3.2 TropeTwist — the formal CS version
[arXiv:2204.09672](https://arxiv.org/abs/2204.09672) (FDG'22): represents a narrative as a **narrative graph of interconnected tropes**, nodes **typed by base** (hero=rectangle, conflict=diamond, enemy=hexagon, plot-device=circle), edges unidirectional / bidirectional / **entailment**. Graphs are **generated and scored for coherence + interestingness** (MAP-Elites over graph grammars). Proves the meso layer can be a **machine-checkable typed graph** — aligning with LoreWeave's Neo4j `(:Event)` substrate (`:CAUSES`, `:HAPPENS_BEFORE`).

### §3.3 Research convergence (carried from prior art)
KG-grounded generation (arXiv:2505.24803 — editable KG, "strong sense of control"; arXiv:2508.03137 — KG + literary-theory "story-theme-obstacle," dual memory anti-drift) independently arrives at *graph + literary structure + revision loop*. The motif library is the **literary-structure** half made first-class.

---

## §4 Self-enrichment — the "analyze → template" flywheel (mandatory, per PO)

The PO requirement: the system must **analyze its own corpus and mint new templates**, so the library grows itself rather than being hand-seeded forever. The substrate already exists:

```
chapters (book-service)
   │  outbox event (existing extraction trigger)
   ▼
knowledge-service extraction → Neo4j  (:Event)-[:CAUSES|:HAPPENS_BEFORE]->(:Event)   ← ALREADY PRODUCTION
   │
   ▼
motif MINING (new): frequent-sequence over event chains
   • PrefixSpan / SPADE / GSP for ordered event-function sequences   (§2.3 plot graphs)
   • frequent-subgraph mining for branching motifs                    (TropeTwist-style)
   │  candidate motifs (abstracted: entities → role slots)
   ▼
calibrated LLM-as-judge (loreweave_eval) — score coherence/reusability, label, dedup   ← ALREADY PRODUCTION
   │
   ▼
motif library (new)  ← book-tier draft → user promotes → publish to system (§ tenancy)
```

**Cold-start caveat (locked):** frequent-pattern mining needs a corpus; on 1–2 books it yields noise. → **Phase 1 seeds motifs by hand** (a tu-tiên/báo-thù pack from §2.5, abstracted onto the schema). **Phase 2 turns on mining** once enough books are extracted. The flywheel reuses the *entire* existing extraction + eval stack — no new pipeline, only a mining stage + the library tables.

**Abstraction is the hard step**, not the mining: a mined chain is concrete ("Lin fell off Azure Cliff, met Ghost-Elder, got the Nine-Yang Manual"). To be a reusable motif it must be **lifted to roles + conditions** ("Protagonist falls into [isolated-locale] → encounters [Mentor:dying] → acquires [Legacy:technique] → pre: protagonist weak/humiliated; post: power+, debt to mentor"). That lift is an LLM step, judge-gated.

---

## §5 Design lessons (fed into the spec)

1. **Encode a generic schema, seed with genre instances.** Schema = Propp-function-like *motif type* (role slots + ordered sub-beats + pre/post-conditions + emotion/tension target + genre tags). Instances = the web-novel packs. *Never hardcode the packs into service code — they are data rows.*
2. **Layer the library to match the existing altitudes** (§2): the motif library is the **meso** layer between `structure_template` (macro) and `outline_node`/`canon_rule`/`style_profile` (scene/fine). The planner consumes top-down: template beat → motif chain → bound scenes.
3. **Tension/emotion is a first-class control signal** — already in `outline_node.tension`; oh-story's −9…+9 confirms it. A motif declares a target tension/emotion curve; adaptive-K already keys on tension.
4. **Roles bind to glossary entities** (Greimas/Propp) — a motif's role slots resolve to the book's cast at apply-time, reusing the `present_entity_ids` resolution the decompose planner already does.
5. **Composition relation (ATU)** — a "pattern" (large) is a named composition of motifs (small); store the composed-of edge so packs nest.
6. **Retrieval = brute-force cosine first** (the `reference_source` precedent): libraries are small (dozens–hundreds of motifs); embed each motif's abstract description via provider-registry `/internal/embed`, store `REAL[]`, top-K in app code. Defer pgvector/Neo4j-vector until scale demands.
7. **Constrain plot hard, prose soft** (§0.5) — the motif governs Event/sequence; `style_profile`/`voice_profile` keep prose under separate, looser control. Judge-gate catches formulaic output.
8. **Mining is Phase 2** — ship hand-seeded Phase 1 first; it directly fixes the weak-planner pain and is eval-gateable against the existing A3 decompose baseline.

---

## §6 Vocabulary → LoreWeave surface mapping (quick reference)

| Formalism | Reusable as | LoreWeave surface | Status |
|---|---|---|---|
| Save the Cat / Hero's Journey beats | macro beat slots | `structure_template.beats[]` | ✅ have |
| Greimas 6 actants / Propp 7 roles | motif **role slots** | NEW `motif.roles[]` → glossary entity bind | ❌ |
| Propp 31 functions / Polti 36 situations | motif **type vocabulary** | NEW `motif.kind` / `function_key` | ❌ |
| Plot graphs / MEXICA pre-post conditions | motif **conditions + legal succession** | NEW `motif.preconditions/effects` + graph | ❌ |
| Thompson Motif-Index IDs / ATU compose | **hierarchical motif category + composed-of** | NEW `motif.category` + `motif_link` | ❌ |
| Web-novel 套路 / 爽点 / 打脸 / cultivation | **seed instances** (genre packs) | NEW seeded `motif` rows (system tier) | ❌ |
| 200-constraint Event/Style/Char/Setting | **fine per-scene tags** | `canon_rule` + `style_profile` + `voice_profile` + `tension` | ⚠️ partial |
| oh-story 13 hooks / 6 emotion arcs | motif **sub-kinds** | NEW `motif.kind IN (hook, emotion_arc, …)` | ❌ |
| Lehnert plot units / emotion −9…+9 | **emotion/tension target** | `outline_node.tension` + NEW `motif.tension_target` | ⚠️ partial |

---

## §7 Source list

**Control thesis / constraints:** Style over Story — 200 constraints ([arXiv:2510.02025](https://arxiv.org/abs/2510.02025)); LLM Chinese-literature homogeneity ([arXiv:2603.14430](https://arxiv.org/html/2603.14430v1)); Survey on LLMs for Story Generation, EMNLP'25 Findings ([pdf](https://aclanthology.org/2025.findings-emnlp.750.pdf)); Iterative suspense planning ([arXiv:2402.17119](https://arxiv.org/pdf/2402.17119)).
**Classical narratology:** Propp 31 functions ([outline](https://www.researchgate.net/publication/319293980)); Greimas actantial model ([Wikipedia](https://en.wikipedia.org/wiki/Actantial_model)); Polti 36 situations ([storyanddrama](https://www.storyanddrama.com/the-36-dramatic-situations-of-georges-polti/)); Thompson Motif-Index ([Wikipedia](https://en.wikipedia.org/wiki/Motif-Index_of_Folk-Literature)); Aarne–Thompson–Uther index ([Wikipedia](https://en.wikipedia.org/wiki/Aarne%E2%80%93Thompson%E2%80%93Uther_Index)).
**Computational narrative:** Story-generation survey (Scheherazade/MEXICA/plot units) ([ResearchGate](https://www.researchgate.net/publication/299401833)); Plot Units, Lehnert ([Semantic Scholar](https://www.semanticscholar.org/paper/7f4955f65531ff06faed6e97540419a22ba4deee)); plot graphs / inference ([Riedl & Li](https://faculty.cc.gatech.edu/~riedl/pubs/purdy-icids16.pdf)); TropeTwist ([arXiv:2204.09672](https://arxiv.org/abs/2204.09672)).
**KG-grounded (carried):** Guiding Storytelling w/ KG ([arXiv:2505.24803](https://arxiv.org/abs/2505.24803)); KG + Literary Theory ([arXiv:2508.03137](https://arxiv.org/pdf/2508.03137)).
**Web-novel craft:** oh-story-claudecode ([github](https://github.com/worldwonderer/oh-story-claudecode)); 黄金三章 ([知乎](https://zhuanlan.zhihu.com/p/34341209)); cultivation tropes ([Xiuxian Guide](https://xiuxian0.com/web-novels/cultivation-novel-tropes/)); Chinese web-novel tropes ([lightnovelsai](https://lightnovelsai.com/blog/chinese-tropes-in-light-novels-and-web-novels/)).
