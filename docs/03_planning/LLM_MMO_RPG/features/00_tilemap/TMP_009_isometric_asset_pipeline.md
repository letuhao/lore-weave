# TMP_009 — Isometric Asset Pipeline (NAG + canonical-tile composite)

> **Conversational name:** "Isometric Asset Pipeline" (TMP-ASSET). The bridge from
> the engine's *semantic* tile data (`TerrainKind`, `BiomeObjectType`, object kinds)
> to *visual* sprites the Phaser 3 client can render. Gen-time anchor = NAG +
> hardened negative (Flux dev distilled at CFG=1.0); post-process anchor = scale
> normalise + composite onto one canonical 2:1 dimetric diamond tile.
>
> **Category:** TMP — Tilemap Foundation
> **Status:** **DRAFT 2026-05-23** (opens reserved slot TMP_009 / TMP-D6; initiated by PO during V2 PoC asset exploration; pipeline exercised on 1 entry × 3 biomes × 3 seeds the same day — n=9, mixed results, **NOT yet production-ready**; see §3.1 results table + §7 + §11)
> **Owns:** TMP-39 catalog entry (TMP-D6 V2 sprite atlas pipeline) + the static-prop
> production pipeline + atlas-manifest schema + the additive `facing` placement
> field. Actor multi-facing path is reserved but unresolved (TMP-ASSET-Q10).
> **Sibling pattern:** MAP_002 (planned shared image-asset pipeline) — TMP_009 is
> the tilemap-specific instance; if MAP_002 lands first, fold the shared logic up.
>
> **Earlier draft note:** the first draft of this doc proposed a Blender mesh-anchor
> ("golden rig") as the primary solution. That hypothesis was abandoned when (a)
> the team lacked Blender skill (TMP-ASSET-Q8) and (b) NAG + canonical-tile
> composite was found sufficient on the static-prop spike. The mesh path is
> retained only as a deferred fallback for actor multi-facing (§3.3 method C).

---

## §1 Why this exists

The engine is feature-complete and emits a **complete V1+30d map as pure data** —
`TerrainKind` per tile, `TilemapObjectPlacement` records (kind + anchor + value +
`biome_object_type`), zone/biome selections. There is **no visual layer**: nothing
the player sees. This is by design — the core product is text-LLM-driven and
consumes the map through L4 narration (TMP_008). But a graphical Phaser 3 client
(TMP-Q4 locked: Phaser 3 FE engine) needs sprites.

**The problem this doc solves is *consistency*, not generation.** Free-form image
generation (SD / ComfyUI) drifts on perspective, scale, lighting, and line weight
between runs. A pile of independently-generated 2.5D assets looks chaotic when laid
on one tilemap — the exact symptom observed in the existing rough-asset batch.

**Root cause (revised after spike, 2026-05-23):** the existing batch was generated
with Flux dev distilled at CFG=1.0, where ComfyUI's `cfg1_optimization` silently
skips the uncond pass — meaning the negative prompt that listed anti-ground terms
was never enforced. The model defaulted to its strong training prior ("isometric
2.5D strategy map flora sprite" ⇒ prop on ground), producing per-seed drift in
base treatment, scale, and species. The earlier hypothesis that the root cause was
"no shared geometric ground truth" turned out to be wrong: enforcing the negative
plus normalising scale/anchor in post is sufficient.

**Solution (validated):** a two-layer anchor.

1. **Gen-time** — the in-tree `NAGuidance` node restores the uncond pass at CFG=1.0
   and enforces a hardened negative that explicitly forbids ground / rocks /
   platform / pedestal / iso-base / terrain / soil / cast-shadow. See §3.1.
2. **Post-process** — every prop is background-stripped, scaled to a fixed target
   height, and composited onto ONE canonical 2:1 dimetric diamond tile. Any small
   residual SD bake-in is absorbed by the canonical tile underneath. See §3.2.

Same Flux model, same LoRA, same CFG=1.0; the upgrade is a one-node workflow patch
plus a Python composite step. This mirrors the engine's determinism discipline
(record method + model + seed → reproducible re-run).

---

## §2 Render target lock

| Decision | Value | Rationale |
|---|---|---|
| Client engine | **Phaser 3** | TMP-Q4 locked. |
| Projection | **2:1 dimetric** ("game isometric") | Pixel-snaps cleanly; true-iso 30° (1.732:1) gives aliased tile edges. |
| Base tile footprint | **128 × 64 px** (authoring); 64 × 32 px pixel-art variant reserved | 2:1 ratio; power-of-two friendly for atlas packing. |
| Camera | Orthographic, `rotX ≈ 30°`, `rotZ = 45°`, fixed distance | The single source of projection consistency. |
| World scale | 1 tile = 1.0 world-unit (fixed) | Kills cross-asset scale drift. |
| Sprite anchor | **bottom-center of the tile diamond** | Depth-sort by `x + y` (painter's algorithm). |
| Depth sort key | `(x + y)`, ties broken by `y` then object layer | Standard iso draw order. |

**Generator data stays valid.** Isometric is a *projection* of the existing flat
`(x, y)` grid (`screen_x = (x − y)·tw/2`, `screen_y = (x + y)·th/2`). No placer
rewrite. The only engine change is one additive field (§4.3).

---

## §3 The anchor — validated 2026-05-23

For **static props** (terrain + biome objects + most placed objects), the validated
quality-control device is a **two-layer anchor**:

### 3.1 Generation-time anchor — NAG + hardened negative

Flux dev distilled requires CFG=1.0; at CFG=1.0 ComfyUI's `cfg1_optimization` skips
the uncond pass, so a standard negative prompt is silently ignored — root cause of
the "lộn xộn" baked-in ground in the existing `homm3-bundle` (research §1, TMP-ASSET-Q9).

The in-tree node **`NAGuidance`** (`comfy_extras/nodes_nag.py`) patches the model:
it calls `disable_model_cfg1_optimization()` so the uncond pass runs, then computes
guided attention `z_pos · s − z_neg · (s−1)` with L1 normalization. Defaults
`nag_scale=5.0`, `nag_alpha=0.5`, `nag_tau=1.5`.

A **hardened negative** listing ground / rocks / platform / pedestal / iso-base /
terrain / soil / grass-tuft / cast-shadow terms is what NAG enforces. Without the
hardened terms NAG has nothing strong to suppress; without NAG the hardened terms
have no effect at CFG=1.0. Both halves are required.

**Empirical results (1 entry × 3 biomes × 3 seeds = 9 outputs, 2026-05-23):**

| Biome | Clean | Partial | Failed | Notes |
|---|:-:|:-:|:-:|---|
| `abyss_chaos_rift` (dark / violet palette) | 3 | 0 | 0 | s303 silhouette drift (pine vs bush) but base sạch |
| `grassland_temperate` (light / temperate) | 1 | 1 | 1 | s202: iso grass platform with flowers baked in |
| `snow_frost` (cold / pale) | 0 | 1 | 2 | s101: subject drift to snow-covered rock pile (no shrub); s202/s303: snow patch + grass baked in |

**Honest verdict:** NAG is **biome-dependent**, not a universal fix. The dark
`chaos_rift` palette + `dark_fantasy_digital_v11` LoRA + NAG aligned cleanly
(3/3 clean). On lighter biomes the model's training prior asserts itself — light
biomes have a stronger "prop-on-ground" training signal that NAG with default
`nag_scale=5.0` can dampen but not eliminate. `snow_frost` is the worst case:
the biome positive hint ("frost rimmed dormant twig bundles") interacts with the
no-ground negative such that the model sometimes abandons the shrub subject
entirely (s101).

**What NAG IS doing reliably across biomes:** preserving the LoRA painterly style
+ producing valid prop subjects most of the time + softening (but not killing)
the ground bake-in. It is *necessary but not sufficient* for cross-biome use.

**Implications for rollout:** raw NAG outputs are NOT production-ready out of the
box. The post-process anchor (§3.2) carries more weight than the original gen-side
breakthrough suggested. See §3.2 caveat about RMBG segmentation being the load-
bearing step, not the white-threshold heuristic.

Levers left to try if quality must improve at gen-time before rollout:
- Higher `nag_scale` (e.g. 8.0) on resistant biomes — at the cost of style
- Biome-specific hardened negatives (different terms per biome palette)
- Two-pass retry on outputs that fail a "subject present + base absent" classifier

### 3.2 Post-process anchor — canonical iso tile composite

Even after NAG, raw outputs vary in scale, anchor, and (per §3.1 finding) often
still carry a baked-in iso platform / grass tuft / snow patch — especially on
light biomes. The post-process step normalises that:

1. **Background strip** — **RMBG-1.4 ONNX** is now the default
   (`experiments/tmp_009/rmbg_cutout.py`, ~1 s/image on CPU, ~7× faster than the
   white-threshold pixel loop and with cleaner edges). Loads from
   `models/rmbg/bria-rmbg-1.4/onnx/model.onnx`; the PyTorch path was rejected
   because `briarmbg.py` is incompatible with transformers ≥5.7 (missing
   `all_tied_weights_keys`). DEBT #8 honest verdict: **RMBG ships as the strip
   step, but does NOT semantically separate "prop only" from "prop on a depicted
   iso platform"** — Flux's baked iso platforms are kept by RMBG because they
   appear connected to the prop subject. Concretely: grassland_temperate s202
   still composites with a visible residual iso platform after RMBG. The proper
   fix for that class of failure is **SAM2 text-prompted segmentation** ("plant
   only, no ground") — opened as a separate spike, not part of debt #8. The
   legacy white-threshold remains accessible via `--no-rmbg` for cases where
   RMBG over-trims (none observed yet on this entry).
2. **Tight crop** to the opaque bounding box.
3. **Optional bottom-trim** — drop a small fraction (~15-20%) of the bbox bottom
   when residual ground tuft survives RMBG. Magic number; tune per asset class.
   Should be a last-resort heuristic on top of RMBG, not the primary tool.
4. **Scale normalize** — resize so the prop height matches a fixed target (e.g.
   `prop_target_h = 384 px` for a 256×128 authoring tile). Kills inter-seed scale drift.
5. **Composite onto a single canonical 2:1 dimetric diamond tile** (§2 projection),
   anchored bottom-centre of the prop on the diamond's visual centre.

**Validation status:** scale + anchor normalisation works (verified on chaos_rift
3 seeds, RMBG path). Background strip swapped to RMBG-1.4 ONNX 2026-05-23 (DEBT
#8 closed); RMBG produces cleaner cutouts on already-clean gen outputs but does
NOT rescue the gen-fail cases where Flux baked a coloured iso platform — that
remains a hard problem requiring either better gen-side (per-biome NAG tuning,
two-pass retry) or a semantic-aware segmentation step (SAM2 text-prompted, opened
as a separate spike).

### 3.3 Actors — multi-facing (UNRESOLVED, TMP-ASSET-Q10)

NAG does NOT solve actor multi-facing. Flux generates one view at a time; asking it
for "the same character from the north" hallucinates a new character. Static props
need 1 facing, so §3.1-§3.2 ships them. **Actors with N facings still require a
separate spike** (not yet run). Three candidate paths, ranked by effort:

| # | Method | Tooling | Effort | Status |
|---|---|---|---|---|
| A | Multi-view diffusion (Zero123++/SV3D) | ComfyUI node + model | Lowest | Not tested — availability not yet confirmed |
| B | Image-to-3D + headless Python render | TRELLIS / Hunyuan3D + pyrender | Medium | Not tested |
| C | Hand-built mesh in Blender | Blender (manual) | High | DEFERRED / advanced (TMP-ASSET-Q8) |

Try method A first when actor work begins.

---

## §4 Asset taxonomy (keyed to engine enums)

Assets join to engine data through the **stable string tags the engine already
exposes** — no new identifier scheme. The renderer looks up a sprite by tag.

### 4.1 Terrain ground tiles — `TerrainKind` (×10)
`grass · forest · mountain · water · sand · snow · swamp · road · rough · subterranean`
(from `TerrainKind::tag()`). Each is **one** iso diamond sprite (static, no facing).
Mesh = flat diamond + minimal relief; trivial geometry. May need 2–4 edge/transition
variants later (deferred §11).

### 4.2 Biome objects — `BiomeObjectType` (×9)
`mountain · tree · lake · crater · rock · plant · structure · animal · other`.
These are the `BiomeSet.templates` obstacles. Each `BiomeId` (e.g.
`grassland_pines`) may map to several sprite variants for visual variety. Static →
**one iso view each** (no facing) unless a designer wants a directional structure.

### 4.3 Placed objects — `TilemapObjectKind`
`Treasure · Town · Mine · Landmark · Monolith · Ferry · Obstacle` (+ V2 `MonsterLair`,
`Decoration`). Mostly static, one view. `Monolith` (teleport pair) and directional
`Structure`s are the first candidates for a `facing`.

### 4.4 Actors (characters / monsters) — future ACT_001 consumer
The **only** category that needs multi-direction + animation, hence the only one
that warrants a rigged/skeletal mesh. **8 facings** (N, NE, E, SE, S, SW, W, NW)
rendered by rotating one mesh 45° per step through the same rig. Static terrain and
props are **never** rigged.

### 4.5 Additive engine field — `facing` (TMP-A8 additive convention)
```rust
/// 8-way isometric facing. Additive (TMP-A8): absent ⇒ None ⇒ renderer uses the
/// single static sprite. Only directional placements (actors, some structures,
/// Monolith) carry it; terrain/obstacle records omit it and stay byte-identical.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Facing { N, Ne, E, Se, S, Sw, W, Nw }

// On TilemapObjectPlacement:
#[serde(default, skip_serializing_if = "Option::is_none")]
pub facing: Option<Facing>,
```
`elevation` (cliffs / multi-level iso) is **deferred** (§11) — single-level iso ships first.

---

## §5 Validated pipeline (4 stages, static props)

```
 [1] generate              [2] strip background     [3] composite             [4] atlas + manifest
 Flux dev Q8 GGUF      →   RMBG (production)    →   tight-crop → scale    →   pack to Phaser atlas
 + dark_fantasy LoRA       transparency.py          normalize → paste on      emit manifest keyed
 + NAGuidance node         white-threshold          ONE canonical 2:1         by engine enum tag
 + hardened negative       (spike fallback)         dimetric diamond tile     (§6)
 CFG=1.0                                            (bottom-center anchor)
```

1. **Generation.** Pack-driven (`scripts/homm3-biome-bundle-batch.py --pack ...`)
   POSTs `/v1/images/generations` to image-gen-service with `model:
   flux1-dev-q8-tree-nag`. That model alias (`config/models.yaml`) routes to
   `workflows/flux_gguf_nag.json`, which is the standard Flux GGUF graph with a
   `NAGuidance` node inserted between `UnetLoaderGGUF` and `KSampler`. The
   service's `inject_loras()` chains a `LoraLoader` (here `dark_fantasy_digital_v11`,
   strength 0.8) between `UnetLoaderGGUF` and `NAGuidance` via `_rewrite_inputs`
   (verified by /history graph trace 2026-05-23). KSampler runs at CFG=1.0, eulers,
   simple, 28 steps, with the hardened negative from §3.1.
2. **Background strip.** **RMBG-1.4 ONNX** (default,
   `experiments/tmp_009/rmbg_cutout.py::apply_rmbg`) — ~1 s/image on CPU, cleaner
   edges than the legacy white-threshold loop. Caveat: RMBG keeps any
   Flux-baked iso platform as part of the subject — see §3.2 + TMP-ASSET-Q11
   (SAM2 spike) for the semantic-separation case.
3. **Composite.** `experiments/tmp_009/poc_static_consistency.py`: tight crop to opaque bbox → optional
   `BASE_TRIM_FRAC` bottom-trim (~0.18, magic; tune per asset class) → resize so
   prop height = `PROP_TARGET_H` (currently 384 px for a 256×128 authoring tile) →
   paste onto the canonical iso diamond at bottom-center.
4. **Atlas + manifest.** TODO. Pack composited PNGs into a Phaser-loadable atlas;
   emit `manifest.json` keyed per §6.

**Service boundary.** Stages 1-2 live in `local-image-generator-service` (FastAPI +
ComfyUI). Stages 3-4 currently live in repo-root spike scripts; will graduate to
`app/postprocess/` once vectorised + RMBG-integrated. The Rust `tilemap-service`
gains exactly one additive field (`facing: Option<Facing>`, §4.5). Phaser client
consumes only atlas + manifest. Three clean seams; no coupling.

---

## §6 Atlas manifest schema

The renderer joins sprites to tile data purely by tag — no positional coupling.

```jsonc
{
  "gen_method": "flux1-dev-q8-tree-nag@workflows/flux_gguf_nag.json",  // provenance: model alias + workflow file used to generate this atlas
  "lora_chain": ["flux/dark_fantasy_digital_v11@0.8"],                  // for reproducibility
  "nag": { "scale": 5.0, "alpha": 0.5, "tau": 1.5 },
  "projection": "dimetric_2to1",
  "tile_px": [128, 64],
  "anchor": "bottom_center",
  "atlas": "tilemap_atlas.png",
  "sprites": {
    "terrain/grass":            { "frame": "grass",        "facing": null },
    "biome/grassland_pines/tree": { "frame": "tree_pine_a", "facing": null, "variants": ["tree_pine_a","tree_pine_b"] },
    "object/town":              { "frame": "town",         "facing": null },
    "object/monolith":          { "frame": "monolith",     "facing": null },
    "actor/goblin":             { "frames": { "n":"goblin_n", "ne":"goblin_ne", "...":"..." }, "facing": "8way" }
  }
}
```
Key convention: `terrain/<TerrainKind.tag>`, `biome/<BiomeId>/<BiomeObjectType>`,
`object/<TilemapObjectKind>`, `actor/<actor_id>`. A missing key ⇒ renderer falls
back to a debug glyph (and SHOULD log) — never a hard crash.

---

## §7 Validation state (2026-05-23 spike)

The full chain has been exercised on **1 entry × 3 biomes × 3 seeds = 9 outputs**:
entry `alpine_dwarf_shrub_cluster`, lane `bush`, biomes `abyss_chaos_rift`,
`grassland_temperate`, `snow_frost`, seeds 101/202/303. **Outcome is mixed** —
see §3.1 results table + §11 AC-2 for the honest tally (4 clean, 2 partial, 3
failed; biome-dependent).

**Artifacts produced (image-gen repo, uncommitted):**
- Workflow — `workflows/flux_gguf_nag.json`
- Model alias — `config/models.yaml` entry `flux1-dev-q8-tree-nag`
- Spike pack — `experiments/tmp_009/nag-cfg1.0-bush-spike-pack.json` (3 biomes; see `experiments/tmp_009/README.md` for v1→v2→v3 mutation log)
- Raw NAG outputs — `outputs/spike-strict-prompt/<biome>/bush/*.png` (9)
- Biome cross-check grid — `outputs/spike-strict-prompt/biome_grid.png`
- chaos_rift composite end-product — `outputs/spike-static-consistency-nag/alpine_dwarf_shrub_cluster_before_after_nag.png`
- grassland composite (shows the double-base failure when RMBG = threshold) — `outputs/spike-static-consistency-nag-grassland/alpine_dwarf_shrub_cluster_before_after_grassland.png`
- NAG-off vs NAG-on A/B (chaos_rift only) — `outputs/spike-strict-prompt/alpine_dwarf_shrub_cluster_original_vs_strict.png`

**Measurements (this session, RTX 4090 24 GB):**
- Gen wall-clock under NAG: **~57 s / image** at 1024×1024, 28 steps, euler/simple. Implication: full bundle (~2 445 images) would take ~39 GPU-hours.
- VRAM: idle (model resident) **~16 GB**; peak during NAG sampling **~22 GB / 24 GB (89%)**; delta vs idle ~+6 GB. Headroom is tight on 24 GB and **will OOM on smaller GPUs** (RTX 4070/4080 12-16 GB) without a smaller Flux quant. Document `vram_estimate_gb` in `config/models.yaml` is currently `10` for `flux1-dev-q8-tree[-nag]` — should be updated to reflect the empirical 22 GB peak.
- Post-process: RMBG-1.4 ONNX on CPU **~1 s/image**, ~7× faster than the legacy white-threshold pixel loop (3-5 s/image) and with cleaner edges. Full pipeline (gen + RMBG + composite) is dominated by gen — RMBG is no longer the bottleneck.

**What still needs work before rollout (see §11 + DEBT items, closed-this-session ones marked ✅):**
1. ✅ **DEBT #4** — n=9 cross-biome reveals NAG is biome-dependent, not universal. NOT shipping as-is for light/cold biomes without further mitigation.
2. ✅ **DEBT #5** — gen ~57 s/image, VRAM ~22 GB peak/24 GB.
3. ✅ **DEBT #8** — RMBG-1.4 ONNX integrated as default strip step (~1 s/image, ~7× faster than legacy + cleaner edges). Honest caveat (§3.2): RMBG does NOT solve the semantic prop-vs-baked-platform separation that gen-fail cases need.
4. ☐ **TMP-ASSET-Q11** (new, opened by DEBT #8 honest finding) — SAM2 text-prompted segmentation for "prop only, no ground" on the gen-fail cases. Separate spike.
5. ☐ **Per-biome NAG tuning OR fallback strategy** — e.g. higher `nag_scale` on resistant biomes, or two-pass retry of failed outputs. Cheap if Q11 is too expensive.
6. ☐ **TMP-ASSET-Q10** — Actor multi-facing UNRESOLVED.
7. ☐ Cross-entry generalisation — current n=9 covers ONE entry. Production rollout needs at least a handful of entries per biome family to confirm NAG behaviour isn't entry-specific.

---

## §8 Prior art

- **HoMM3 / VCMI** (`.def` sprite format) — adventure-map objects rendered as
  pre-baked iso sprites; actors carry 8-direction frame sets. Direct genre precedent
  (already surveyed for TMP, see `_index.md`).
- **NAG — Normalized Attention Guidance** (Chen et al., 2025) — the in-tree
  ComfyUI implementation (`comfy_extras/nodes_nag.py`) is the validated technique
  for biting negative prompts on distilled few-step models (Flux dev/schnell). It
  operates in attention space, bypassing CFG entirely. Reference implementation +
  Flux demo: `ChenDarYen/ComfyUI-NAG`; native port had an underapply bug per
  `Comfy-Org/ComfyUI#12707`. PAG / Skip-Layer Guidance / FluxPseudoNegative do NOT
  consume user negatives — ruled out by research.
- **ControlNet (depth/normal/lineart) + IPAdapter** — the standard way to constrain
  diffusion to a fixed geometry while transferring a style reference. Reserved for
  the actor multi-facing path (§3.3) and any future mesh-anchored upgrade.
- **Blender-to-sprite "render farm" pipelines** — long-standing technique for
  consistent iso 2D from 3D meshes (one ortho camera, rotate object for facings).
  Deferred (TMP-ASSET-Q8): keep as an advanced upgrade if NAG+composite is later
  found insufficient for actors.

---

## §9 Open questions / deferrals

| ID | Question | Disposition |
|---|---|---|
| TMP-ASSET-Q1 | True-iso 30° vs 2:1 dimetric | **Locked 2:1 dimetric** (§2) — pixel hygiene + Phaser convention. |
| TMP-ASSET-Q2 | Terrain edge/transition tiles (auto-tiling) | **Deferred** — ship flat per-kind tiles first; add Wang/blob tiles when seams show. |
| TMP-ASSET-Q3 | `elevation` / multi-level cliffs | **Deferred** — single-level iso first; reopen with a height field if design needs it. |
| TMP-ASSET-Q4 | Actor animation (walk cycles), not just facings | **Deferred to ACT_001 consumer** — TMP_009 covers static + 8-facing stills. |
| TMP-ASSET-Q5 | Atlas count / streaming (one mega-atlas vs per-biome) | **Deferred** — start single atlas; split when it exceeds GPU texture limits. |
| TMP-ASSET-Q6 | Where does the pipeline repo live | **RESOLVED 2026-05-23** → `G:\Works\local-image-generator-service` (FastAPI + ComfyUI backend, OpenAI-style images API, pack-driven batch runner). |
| TMP-ASSET-Q7 | Mesh-anchor vs tighten the existing Flux pipeline | **RESOLVED 2026-05-23 → tighten the existing Flux pipeline:** the gen-side fix is NAG + hardened negative (§3.1), the post-process fix is the canonical-tile composite (§3.2). Mesh-anchor is NOT used; canny base-plate is also NOT used (turned out unnecessary once NAG was added). For actors see Q10. |
| TMP-ASSET-Q10 | Actor 8-facing rendering path (NAG alone does not solve multi-view) | **UNRESOLVED** — separate spike required. Candidates ranked: (A) multi-view diffusion (Zero123++/SV3D in ComfyUI — availability not confirmed); (B) image-to-3D (TRELLIS/Hunyuan3D/TripoSR) + headless pyrender; (C) Blender mesh (deferred / advanced per Q8). Try A first when actor work begins. |
| TMP-ASSET-Q11 | Semantic "prop only, no depicted ground" segmentation for biomes where NAG fails to suppress baked-in iso platforms | **UNRESOLVED** — DEBT #8 (RMBG-1.4) closed the foreground/background separation but RMBG keeps any iso platform Flux drew as part of the subject. Proposed approach: **SAM2 text-prompted segmentation** ("plant only / leaves and trunk only, exclude ground tile / iso platform / grass") to extract the prop mask, then apply that as the alpha before the composite step. Models already at `models/sam2/`. Separate spike when light/cold biome rollout becomes urgent. |
| TMP-ASSET-Q8 | Does the anchor require Blender? | **RESOLVED 2026-05-23 → no.** Team lacks Blender skill; §3 method A (Zero123++/SV3D in ComfyUI) needs zero Blender. Method B uses Python `pyrender`. **Blender (method C) deferred to advanced**, only if A+B insufficient. |
| TMP-ASSET-Q9 | How to enforce a biting negative prompt on Flux dev distilled (CFG locked at 1.0)? | **RESOLVED 2026-05-23 → NAG (Normalized Attention Guidance).** ComfyUI core `comfy_extras/nodes_nag.py` exposes the `NAGuidance` node (model-patch, experimental). Inserting it between `UnetLoaderGGUF` and `KSampler` calls `disable_model_cfg1_optimization()` so the uncond pass executes at CFG=1.0; attention output is then `z_pos·s − z_neg·(s−1)` with L1 normalization. Verified empirically on `abyss_chaos_rift / alpine_dwarf_shrub_cluster` × 3 seeds: 90% removal of baked-in ground + species drift simultaneously locked + LoRA style preserved. Defaults `nag_scale=5.0, nag_alpha=0.5, nag_tau=1.5` (in-tree). PAG/SLG/FluxPseudoNegative do NOT consume user negatives, ruled out by research. |

## §10 Build prerequisites + existing-pipeline findings (inspected 2026-05-23)

**Home repo resolved:** `G:\Works\local-image-generator-service` — a full image-gen
service (FastAPI `app/`, ComfyUI backend `app/backends/comfyui.py`, OpenAI-style
`/v1/images/generations`, LoRA management, queue, **pack-driven batch runner**).

**Existing asset batch (the "rough/inconsistent" set):** `outputs/homm3-bundle/` —
**2445 PNGs**, Flux-generated (`flux1-dev-q8-tree` + `dark_fantasy_digital_v11` LoRA),
organized by **15 biomes × lanes (bush/misc/mushroom/structure/terrain/trees) × entry
× seed (101/202/303)**, prompts already target "isometric 2.5D ... HoMM3-inspired ...
white backdrop for alpha", `transparent_background: true`.

**Diagnosis confirmed by inspection:**
- **Style is good, keep it** — Flux + dark-fantasy LoRA gives coherent HoMM3-ish
  painterly art. Reuse as IPAdapter / style-LoRA reference.
- **Geometry is inconsistent** — same entry across seeds drifts camera angle, base
  treatment (rocky mound vs iso grass diamond), and scale. Props won't sit together.
- **Terrain isn't tile-shaped** — framed square "pit floor" images with baked edge
  walls, not seamless iso diamonds.
- **Root cause = no geometric ground truth** (validates §1). text2img can't fix it.

**Capability inventory (corrected after inspecting `models/`):**
- **ControlNet models already present** (only canny is *wired* in `config/models.yaml`,
  but the model files exist): `diffuserscontrolnet-depth-sdxl`,
  `noobaiXLControlnet_epsDepthMidasV11` (depth), `noobaiXLControlnet_epsLineartAnime`
  (lineart), `controlnet-union-sdxl-1.0-promax` (canny/depth/normal/lineart union),
  plus canny. → depth/lineart/union need only a **workflow JSON + models.yaml entry**,
  **no downloads**.
- **IPAdapter** (`models/ipadapter/`), **RMBG** (background removal → clean cutouts),
  **SAM2** (masking) all present.
- **Rough batch** located (`outputs/homm3-bundle`, 2445 imgs) — ready as style ref.

**Actual gaps (post-spike, after NAG was validated as the gen-side fix):**
1. **Static-prop path** — ⚠ exercised end-to-end on n=9 (§7), **not yet
   production-ready**. The implementation landed as: in-tree `NAGuidance` node +
   hardened negative (§3.1) + canonical-tile composite (§3.2). The fixed canny
   base-plate originally proposed was NOT used — NAG handled the gen-side fix
   directly. NAG is biome-dependent (clean on dark palettes, weaker on light/cold)
   so RMBG (DEBT #8) carries more weight than first thought — see §3.2.
2. **Production-shape clean-up before rollout** — DEBT #4 (n>1 generalisation),
   DEBT #5 (gen time + VRAM measurement), DEBT #8 (vectorize / RMBG-swap the
   background strip). See §11 AC-7.
3. **Actor multi-view path** — UNRESOLVED (TMP-ASSET-Q10). Availability of
   SV3D/Zero123++ models + nodes in the clean ComfyUI stack not yet confirmed.
4. **Blender** — NOT required (TMP-ASSET-Q8); advanced-only.

**Net:** static path validated on 1 entry; needs broader validation + perf
measurement + RMBG swap before rolling NAG into the production bush/biome/terrain
packs. Actor path is a separate spike.

## §11 Acceptance criteria

Each AC is annotated with current status: ✅ met / ⚠ partially met / ☐ open.

- **AC-1 (gen graph)** ✅ — The `flux_gguf_nag.json` workflow places `NAGuidance` between `UnetLoaderGGUF` and `KSampler`, and `inject_loras()` inserts the LoRA chain between `UnetLoaderGGUF` and `NAGuidance` via `_rewrite_inputs`. Verified by `/history` graph trace 2026-05-23: chain was `UnetLoaderGGUF[1] → LoraLoader[11]/dark_fantasy_digital_v11@0.8 → NAGuidance[10]/scale=5.0,α=0.5,τ=1.5 → KSampler[6]@CFG=1.0`.
- **AC-2 (gen consistency)** ⚠ — Cross-biome validation (1 entry × 3 biomes × 3 seeds = 9 outputs, 2026-05-23): NAG is **biome-dependent**, not universal. Tally: 4/9 clean, 2/9 partial, 3/9 failed. Clean on `chaos_rift` (3/3); mixed on `grassland_temperate` (1 clean, 1 partial, 1 iso-platform baked); poor on `snow_frost` (0 clean, 1 subject drift to rock pile, 2 base baked). LoRA style preserved across all biomes; subject preserved except `snow_frost / s101`. **Not production-ready without either (a) a working RMBG post-process step to absorb residual bases (DEBT #8) or (b) per-biome NAG/negative tuning.**
- **AC-3 (composite normalises)** ✅ — `experiments/tmp_009/poc_static_consistency.py` reproducibly places 3 raw seeds on a single canonical 2:1 dimetric tile at bottom-center, identical scale. Verified by `outputs/spike-static-consistency-nag/*_before_after_nag.png`. *But background strip is not currently load-bearing on light biomes — see §3.2 + DEBT #8.*
- **AC-4 (engine additive)** ☐ — The `facing: Option<Facing>` field on `TilemapObjectPlacement` is specified (§4.5) but not yet implemented in `services/tilemap-service`. Implementation is gated until any consumer (actor or directional structure) needs it.
- **AC-5 (atlas join)** ☐ — Manifest schema is specified (§6) but no atlas has been packed yet (stage 4 not implemented). The "missing key → debug glyph fallback" behaviour will be enforced in the renderer, also TBD.
- **AC-6 (actor multi-facing)** ☐ — UNRESOLVED, see TMP-ASSET-Q10. NAG alone does not solve this; awaits a separate actor-path spike.
- **AC-7 (performance)** ⚠ — Measured 2026-05-23 on RTX 4090: gen ~57 s/image (=~39 GPU-h for full 2445-image bundle), VRAM peak ~22 GB / 24 GB during NAG sampling. Tight on 24 GB; will OOM on ≤16 GB cards (Q8 GGUF chunk + Flux UNet + LoRA + NAG attention buffers). `config/models.yaml.vram_estimate_gb: 10` understates the actual peak by 2.2× — should be reconciled before any auto-scheduled multi-job rollout. Background strip step is now RMBG-1.4 ONNX on CPU (~1 s/image, ~7× faster than the prior pixel loop) — DEBT #8 closed, though RMBG does NOT solve the semantic prop-vs-baked-platform separation (see §3.2 honest note).
