# W2 — Planner select + bind (DETAILED DESIGN)

> **Workstream:** W2 of the Narrative Motif Library parallel build · **Service:** `composition-service` (Python/FastAPI) · **Phase:** P1 (Wave 1).
> **Spec:** [`2026-06-26-narrative-motif-library.md`](../../specs/2026-06-26-narrative-motif-library.md) — read **§R1.1/R1.4** (2-tier + schema), **§3.1** (planner L2), **§R2.6** (swap-after-gen), **§16** (dials), **§13** (MCP line).
> **Master plan:** [`2026-06-26-motif-library-master-plan.md`](../2026-06-26-motif-library-master-plan.md) — F0 §3.3 (`retrieve()` signature I consume), §4 W2 def, §7 risk guards (R3/F1/H-4/B1).
> **Ground truth read for this design:** `engine/plan.py` (A3 L1/L2, `parse_scenes`, `_resolve_cast`, the tolerant parse + degrade), `engine/adaptive_k.py` (the 0..100 tension gate), `routers/plan.py` (`decompose_preview`/`decompose_commit`), `mcp/server.py` `archive_node`/`restore_node` nodes, `db/repositories/outline.py` (`archive_node`/`restore_node`/`_insert_decomposed_tree`/`get_node`), `routers/actions.py` (the Tier-W confirm pattern).
>
> **Status:** DESIGN. The doc IS the deliverable. Code shapes are concrete and grounded against the real files cited above. `MotifRetriever.retrieve` is **mocked** until W3 lands (master §2: W2 builds against the frozen F0 signature only).

---

## §1 Scope + the consumed `retrieve()` contract

### §1.1 What W2 owns (disjoint file ownership — master §4)

| File | New/edit | Role |
|---|---|---|
| `engine/motif_select.py` | **NEW** | The select+bind core: `retrieve → select(adaptive-K aware) → bind(role→cast) → motif_application`. The NO-MATCH fallback signal. The swap-after-gen plan/undo. The cost re-estimate hook. **Sole owner.** |
| `engine/plan.py` | **edit (sole owner)** | The L2 rework — splice motif select+bind into `one_chapter`; thread `motif_application` rows + `match_reason` into the result dataclasses; **strict back-compat when motifs disabled**. |
| `engine/adaptive_k.py` | **edit (sole owner)** | The tension **1-5 ↔ 0-100** reconcile: a new `motif_tension_to_scale()` mapper + a `bound_tension` parameter into `adaptive_k` so a bound motif's beat-tension drives K. |
| `routers/plan.py` | **edit (preview fields only)** | `decompose_preview` passes the motif toggle + book genres/language into `decompose`; `decompose_commit` persists `motif_application` rows + the swap `PATCH …/motif` endpoint. Preview DTOs gain `motif_id/motif_name/role_bindings/motif_source/match_reason`. |
| `tests/unit/test_motif_select.py` | **NEW** | Unit coverage for select/bind/fallback/reconcile/swap. |
| `scripts/eval_motif_planner.py` | **NEW** | 3-way eval-gate (motif vs A3-invent vs A3+plot-nudge). |

**Not W2's:** the `retrieve()` *impl* + embedding (W3), the `Motif`/`MotifApplication` models + the migration + `motif_application` repo write method signature (F0), the CRUD/clone routes (W1), the MCP tool *bodies* (W4) — but W2 **defines the `composition_motif_bind` engine** that W4's tool calls (the bind logic lives in `motif_select.py`; W4 wires the MCP envelope to it). See §4.4 for the seam.

### §1.2 The `retrieve()` contract I consume (frozen in F0 §3.3 — I do NOT change it)

```python
# db/repositories/motif_retrieve.py  (W3 implements; W2 consumes the signature ONLY)
class MotifRetriever:
    async def retrieve(
        self, caller_id: UUID, *,
        book_id: UUID, project_id: UUID,
        genre_tags: list[str], language: str,
        beat_role: str | None, tension: int | None,   # tension is the chapter's 0..100 INTENT signal
        prev_effects: list[str],                       # the PREVIOUS bound motif's effects[] (legal succession)
    ) -> list[MotifCandidate]: ...

# MotifCandidate (F0 frozen):
#   motif:        Motif            # full row incl. roles[], beats[], effects[], tension_target(1..5), language
#   score:        float            # cosine(summary-embedding, chapter-intent-embedding), already ranked desc
#   match_reason: dict             # {"tension": float, "genre": float, "precond": float, "cosine": float}
```

**Contract obligations W3 guarantees (I rely on, I do not re-implement):**
1. Results are **already filtered** in SQL: `status='active'` only, `genre_tags ∩ book.genre_tags` non-empty, the tier predicate (system | public | owner — R1.1 read predicate), and `language` match. **W2 never re-filters status/tier/genre** — that would duplicate W3 and drift.
2. Results are **already sorted by `score` desc** (cosine over the platform embedding model — R1.1.2, one space, so cross-tier cosine is valid). W2's tie-break (§5) is the **only** re-ordering W2 applies, and only within an exact-score tie.
3. `prev_effects` is W3's legal-succession input; the *returned* `match_reason["precond"]` is W3's scored verdict on whether `prev_effects ⊨ candidate.preconditions`. **W2 surfaces `precond` but does not compute it** — the planner does not re-evaluate preconditions itself (no predicate DSL; §11 "conditions = free-text NL, planner matches semantically", DECIDED).
4. An empty list (`[]`) means **no candidate passed the SQL pre-filter** — distinct from a `MotifRetrieverError` raised on infra failure (the fallback matrix, §2.4, separates these two).

**The mock (until W3 lands):** `tests/unit/test_motif_select.py` provides a `FakeRetriever` whose `retrieve()` returns a scripted `list[MotifCandidate]` (or `[]`, or raises) — exactly the four behaviors above. W2 ships and is gated entirely against this fake; R-NODE-P1 (master §6) swaps in the real W3 impl on a live stack-up.

---

## §2 The L2 rework — retrieve → select → bind → write `motif_application`

### §2.1 Where it slots into the REAL `plan.py`

The A3 planner today (`plan.py:301 one_chapter`) does, per chapter, inside the `asyncio.Semaphore(_L2_CONCURRENCY)` fan-out:

```
build_scene_decompose_messages(...)  →  _llm_json(...)  →  parse_scenes(...)  →  ChapterScenes
```

W2 inserts a **retrieve+select+bind stage BEFORE the LLM invent call**, and makes the invent call **conditional**:

```
one_chapter(ch):
  (NEW) if motifs_enabled and ch.beat_role is not None:
          candidate = await select_motif_for_chapter(ch, retriever, prev_effects=carry[thread], ...)
          if candidate is not None:                      # MATCH → bind path
              binding = bind_motif(candidate, cast_index, ch)
              scenes  = scenes_from_motif(candidate, binding, ch, k_ceiling, high_threshold)
              app_row = build_application_row(candidate, binding, ch)   # motif_application (persisted at commit)
              carry[thread] = candidate.motif.effects                   # legal-succession hand-off
              return ChapterScenes(chapter=ch, scenes=scenes, motif=candidate, binding=binding,
                                   application=app_row, warning=binding.warning)
  # NO MATCH (retrieve empty / errored / motifs disabled / connective beat) → today's invent path VERBATIM
  sys2, usr2 = build_scene_decompose_messages(...)
  c = await _llm_json(...)
  ... parse_scenes(...) ... return ChapterScenes(chapter=ch, scenes=..., motif=None, ...)
```

**Key design decisions, each grounded:**

- **Selection is gated on `ch.beat_role is not None`.** A chapter L1 left unmapped (`beat_role=None` — `plan.py:143`) has no structural slot to bind a motif to; it goes straight to invent. This mirrors `adaptive_k`'s own "no beat_role, no bump" stance (no silent inference).
- **`scenes_from_motif` produces the SAME `list[ScenePlan]` shape** `parse_scenes` produces (`plan.py:65 ScenePlan`) — so the downstream commit path (`routers/plan.py` → `_insert_decomposed_tree`) is **unchanged**: a motif-bound scene and an invented scene are indistinguishable at the node-write layer. The only addition is the `motif_application` rows, persisted alongside (§2.6).
- **The invent path is touched in exactly ZERO ways when `motifs_enabled` is false** — the new branch is skipped entirely, the existing lines run verbatim. This is the back-compat guarantee acceptance #4 (`§10`: no-match falls back to invent, no regression) and the eval-gate's fallback-non-regression test (§6.3).

### §2.2 `select_motif_for_chapter` — adaptive-K-aware selection (the SELECT step)

```python
# engine/motif_select.py

@dataclass(frozen=True)
class SelectedMotif:
    motif: Motif                 # F0 model
    score: float
    match_reason: dict           # {tension, genre, precond, cosine}  — surfaced to the author

async def select_motif_for_chapter(
    ch: ChapterPlan, retriever: MotifRetriever, *,
    book_id: UUID, project_id: UUID, caller_id: UUID,
    genre_tags: list[str], language: str,
    prev_effects: list[str],
    min_score: float,            # config: motif_min_score
    high_threshold: int,         # config: plan_high_tension_threshold (70)
) -> SelectedMotif | None:
    """RETRIEVE then SELECT one motif (top-1) for a chapter, or None to fall back.

    SELECT is adaptive-K-aware in the spec sense (§3.1): a HIGH-tension beat WANTS a
    motif (it is exactly where invent fails); a CONNECTIVE beat MAY stay free-form.
    The chapter's tension here is the INTENT-level signal — we do not have per-scene
    tension yet (scenes don't exist until bind), so we derive a chapter tension from
    the beat_role weight (HIGH_WEIGHT_BEATS → high) to feed retrieve()."""
    chapter_tension = _chapter_intent_tension(ch.beat_role, high_threshold)  # §3.3

    try:
        cands = await retriever.retrieve(
            caller_id, book_id=book_id, project_id=project_id,
            genre_tags=genre_tags, language=language,
            beat_role=ch.beat_role, tension=chapter_tension, prev_effects=prev_effects,
        )
    except MotifRetrieverError as exc:                 # infra failure — fallback matrix F1 (errored)
        logger.warning("motif retrieve errored for chapter %s → invent fallback: %s", ch.chapter_id, exc)
        return None
    if not cands:                                      # empty — fallback matrix F1 (retrieve-empty)
        return None

    # CONNECTIVE-beat policy (adaptive-K-aware): a low-weight beat does not FORCE a
    # motif. We still bind one if the top candidate is a strong fit (score well over
    # the floor), but a weak fit on a connective beat → stay free-form (invent reads
    # better than a forced cliché — the §9 "formulaic output" risk made structural).
    top = _pick_top1(cands)                            # tie-break §5
    is_high = (ch.beat_role or "").strip().lower() in HIGH_WEIGHT_BEATS
    floor = min_score if is_high else max(min_score, _CONNECTIVE_FLOOR)  # connective beats demand a higher bar
    if top.score < floor:
        return None
    return SelectedMotif(motif=top.motif, score=top.score, match_reason=top.match_reason)
```

- **Top-1 in auto, top-N in co-write:** auto mode (the planner pipeline) binds the single best (`_pick_top1`). Co-write returns the ranked candidates to the preview so the author picks (§2.5 — the planner emits `candidates[]` in the preview for the bound chapter, top-1 pre-selected). The selection *logic* is identical; only how many survive into the preview differs. This matches `_suggest_for_chapter`'s "candidates + match_reason" payload (§13.1) — **one retrieval core, two entries** (spec §13.3).
- **`_CONNECTIVE_FLOOR`** is a module constant (recommend `min_score + 0.08`, tuned at eval). The point: a connective beat must clear a *higher* bar to earn a motif, so the library doesn't carpet-bomb every transition with a trope.

### §2.3 `bind_motif` — role → cast via `_resolve_cast` (the BIND step)

The spec (§3.1 step 3) says "map `motif.roles[]` → book cast (reuse the present_entity name→id resolution already in plan.py)". The reusable primitive is **`plan.py:181 _resolve_cast`** — it folds names, dedupes ids preserving order, surfaces unresolved. W2 reuses it **without modifying plan.py's copy** (W2 owns plan.py, so it's free to call `_resolve_cast` directly).

```python
# engine/motif_select.py

@dataclass(frozen=True)
class MotifBinding:
    role_bindings: dict[str, str]        # {role_key: glossary_entity_id}   → motif_application.role_bindings
    unresolved_roles: list[str]          # role_keys whose hint matched no cast member (SURFACED, not invented)
    annotations: dict                    # bound info_asymmetry / reversal / alliance_shift  (§15 → motif_application.annotations)
    warning: str | None                  # 'partial_role_bind' when unresolved_roles non-empty, else None

def bind_motif(sel: SelectedMotif, cast_index: dict[str, str], ch: ChapterPlan) -> MotifBinding:
    """Bind each motif role to a book cast entity by NAME HINT, via _resolve_cast.

    A role's binding candidate is its `label`/`constraints` name hints (the role is
    abstract: {key, actant, label, constraints}). We resolve the label against the
    cast roster the SAME way present-entity names resolve. An unbound role is
    SURFACED (unresolved_roles) — never invented as an id (the no-silent-inference
    rule, mirrors present_entity_names_unresolved)."""
    role_bindings: dict[str, str] = {}
    unresolved: list[str] = []
    for role in sel.motif.roles:                       # [{key, actant, label, constraints}]
        key = role.get("key")
        if not key:
            continue
        hints = [h for h in (role.get("label"), *(role.get("constraints") or [])) if isinstance(h, str)]
        ids, miss = _resolve_cast(hints, cast_index)   # reuse plan.py's resolver
        if ids:
            role_bindings[key] = ids[0]                 # first matched cast member fills the slot
        else:
            unresolved.append(key)
    annotations = _bind_annotations(sel.motif, role_bindings)   # §15: info_asymmetry/reversal entities → ids
    warning = "partial_role_bind" if unresolved else None
    return MotifBinding(role_bindings=role_bindings, unresolved_roles=unresolved,
                        annotations=annotations, warning=warning)
```

**Partial-bind is NOT a failure** (this is the F1 matrix's third axis). A motif whose protagonist slot binds but whose `opponent` slot finds no cast member still binds — the scenes are instantiated, the `motif_application` row records the partial `role_bindings`, and `unresolved_roles` is surfaced into the preview (the FE shows the inline cast-picker + "create entity" shortcut, §11 — same affordance as `present_entity_names_unresolved`). The chapter is **bound**, just flagged. We only fall back to invent when there is **no match at all** (§2.4), never on a partial bind.

### §2.4 The NO-MATCH fallback + the F1 matrix (audit F1)

The spec is explicit (§3.1, §10): a no-match chapter falls back to today's invent-path with **no regression**. The audit (master §7, F1) demands the full matrix be designed, not just the happy path. The matrix has three independent axes:

| Axis | Values | Source |
|---|---|---|
| **L1 state** | mapped (`beat_role` set) · **degraded** (`beat_role=None`, L1 LLM failed — `plan.py:296`) | A3 L1 |
| **retrieve result** | candidates · **empty** (`[]`) · **errored** (`MotifRetrieverError`) | W3 contract §1.2 |
| **bind result** | full · **partial** (`unresolved_roles ≠ []`) · n/a (no candidate) | §2.3 |

The 2×3 of {L1}×{retrieve} (bind only applies once a candidate exists) resolves as:

| | retrieve = candidates | retrieve = empty | retrieve = errored |
|---|---|---|---|
| **L1 mapped** | SELECT (§2.2). If score≥floor → BIND (full or partial → bind+flag). If score<floor → **invent**. | **invent** (`warning='no_motif_match'`) | **invent** (`warning='motif_retrieve_degraded'`) |
| **L1 degraded** (`beat_role=None`) | **never reached** — selection is gated on `beat_role is not None` (§2.1); we don't retrieve without a beat slot | **invent** (today's verbatim degrade) | **invent** |

**Every cell that falls back runs the EXISTING invent path unchanged** — the only difference is a per-chapter `warning` token in the preview that tells the author *why* this chapter wasn't motif-bound. Five tokens, distinct for observability:
- `no_motif_match` — retrieve returned `[]` (the library has nothing for this genre/beat).
- `motif_retrieve_degraded` — retrieve raised (infra). Distinguishable from `no_motif_match` so an outage doesn't look like an empty library.
- `motif_below_floor` — candidates existed but the top score < floor (or < connective floor).
- `partial_role_bind` — bound, but some roles unresolved (this is on a **bound** chapter, alongside the binding — not a fallback).
- (existing A3 tokens — `scene_decompose_degraded`, `no_scenes_parsed` — survive unchanged on the invent path.)

> **The degraded-L1 × candidates cell is structurally impossible by the §2.1 gate** — this is the deliberate design that collapses the matrix. We never attempt a bind without a beat_role, so "bound to a degraded chapter" can't occur. The audit's worry (binding a motif onto a chapter whose structural role is unknown) is designed out, not merely tested out.

### §2.5 `scenes_from_motif` — instantiate beats → ScenePlan (no LLM)

The spec (§3.1 step 3) instantiates `motif.beats[]` → scene nodes `{title/intent/tension_target}`. This is **deterministic** (the value of binding: a 7B model can't invent plot-sound scenes, but it doesn't need to — the motif *supplies* the beat structure). The scenes are built from the motif's ordered beats, NOT an LLM call:

```python
def scenes_from_motif(
    sel: SelectedMotif, binding: MotifBinding, ch: ChapterPlan, *,
    k_ceiling: int, high_threshold: int, min_scenes: int, max_scenes: int,
) -> list[ScenePlan]:
    """One ScenePlan per motif beat (ordered), clamped to [min,max]_scenes. tension
    is the beat's tension_target reconciled 1..5 → 0..100 (§3). suggested_k uses the
    SAME adaptive_k as invent, now driven by the reconciled tension + beat_role."""
    beats = sorted(sel.motif.beats, key=lambda b: b.get("order", 0))[:max_scenes]
    present_ids = list(binding.role_bindings.values())          # bound cast → scene present_entities
    out: list[ScenePlan] = []
    for b in beats:
        tens5 = b.get("tension_target")                          # 1..5 (motif scale)
        tension = motif_tension_to_scale(tens5, fallback=sel.motif.tension_target)  # §3 → 0..100
        out.append(ScenePlan(
            title=(b.get("label") or b.get("intent") or "")[:60],
            synopsis=_render_beat_synopsis(b, binding),          # beat.intent with role keys → bound names
            tension=tension,
            present_entity_ids=present_ids,
            present_entity_names_unresolved=[],                  # roles resolved at bind; unbound surfaced separately
            suggested_k=adaptive_k(ch.beat_role, tension, k_ceiling=k_ceiling, high_threshold=high_threshold),
        ))
    # Under-fill guard: a motif with fewer beats than min_scenes is fine (the motif
    # IS the structure); we do NOT pad with invented scenes (that reintroduces the
    # failure mode). The chapter simply has that many beats.
    return out
```

- **`_render_beat_synopsis`** substitutes role keys in the beat's `intent` with the **bound entity names** (e.g. `"{protagonist} confronts {opponent}"` → `"Lin confronts the Sect Elder"`), so the scene synopsis is concrete and grounded — the author sees real names, the packer gets a usable prompt. Unbound role keys are left as the abstract label (graceful — matches the partial-bind flag).
- **No LLM call on the bind path.** This is the latency + cost win: a bound chapter is `O(1)` DB-shaped work, not a 1536-token generation. (The cost re-estimate in §3.3 is about *downstream generate* K, not the plan step.)
- **`min_scenes`/`max_scenes` clamp** mirrors `parse_scenes` (`plan.py:234`) so a motif can't blow past the per-chapter scene cap.

### §2.6 Writing the `motif_application` row (provenance)

The application row is **not** written at preview time (preview is non-persisted — `plan.py:130` "NOT persisted"). It rides the **commit** path, exactly like scene nodes. F0 owns the `motif_application` schema (§R1.4) and the repo write signature; W2 *calls* it from `decompose_commit` and the swap endpoint.

```python
# build the persistable payload during planning (preview carries it for the author to see/edit):
def build_application_row(sel: SelectedMotif, binding: MotifBinding, ch: ChapterPlan) -> dict:
    return {
        "motif_id": str(sel.motif.id),
        "motif_version": sel.motif.version,        # [edge-F3] PIN the bound version — trace shows what was bound, not live
        "chapter_id": str(ch.chapter_id),          # resolved → outline_node_id (the chapter node) at commit
        "role_bindings": binding.role_bindings,     # {role_key: entity_id}
        "annotations": binding.annotations,         # §15 info_asymmetry/reversal/alliance_shift (bound to ids)
    }
```

At commit (`routers/plan.py:decompose_commit`, after `commit_decomposed_tree` returns the created node ids), W2 maps each chapter's `application_row.chapter_id` → the created **chapter** `outline_node_id` and inserts the `motif_application` rows **in the same transaction** as the tree (F0 exposes a `MotifApplicationRepo.insert_many(conn, ...)` that the commit can call on the open connection — this keeps the application ledger atomic with the nodes; an orphan application with no scenes is never created). The row carries `book_id` (per-book scope, R1.1.4) resolved from the Work.

> **Bind target = the chapter node, not each scene.** §R1.4's `motif_application.outline_node_id` references one node; the natural anchor is the **chapter** outline_node (the motif governs the whole chapter's beat-set), with `role_bindings` propagating to every scene's `present_entity_ids`. This matches the swap unit (§4: you swap a *chapter's* motif), and keeps one application row per (chapter, motif) — the anti-repetition count (B1) is then "distinct motif_id per book", clean.

---

## §3 Tension reconcile: motif 1-5 ↔ scene 0-100 (audit R3)

### §3.1 The mismatch, stated precisely

Two scales coexist and the audit (R3) flags that conflating them silently corrupts both K-selection and downstream cost:

| Scale | Range | Where | Source |
|---|---|---|---|
| **Motif tension** | **1..5** | `motif.tension_target` (SMALLINT, §R1.4) + `motif.beats[].tension_target (1..5)` (§2.1) | the motif library (a coarse authoring dial) |
| **Scene/outline tension** | **0..100** | `outline_node.tension` (SMALLINT), `ScenePlan.tension`, the adaptive-K gate | A3 (`adaptive_k.py:11` — "EXISTING 0..100 scale … NOT 1-5"; high gate at 70) |

`adaptive_k` is hard-wired to 0..100 (`high_threshold=70`, mid band `[35,70)`). A bound motif beat carrying `tension_target=4` must NOT be passed to `adaptive_k` as `4` (that reads as "calm", `base=1`) — it must be **mapped to 0..100 first**.

### §3.2 The exact mapping (the sole reconcile point — owned by W2 in `adaptive_k.py`)

```python
# engine/adaptive_k.py   (W2 adds this; sole owner of the file)

# Motif 1..5 → outline 0..100. Anchored so band semantics line up with adaptive_k's
# gates: 5 → 90 (well above the 70 high gate → full ceiling K), 4 → 75 (above 70),
# 3 → 50 (mid band [35,70)), 2 → 30 (below mid), 1 → 10 (calm). Linear-ish with the
# top two both clearing the high gate (a motif's "climax" beats SHOULD earn ceiling K).
_MOTIF_TENSION_MAP: dict[int, int] = {1: 10, 2: 30, 3: 50, 4: 75, 5: 90}

def motif_tension_to_scale(tens5: int | None, *, fallback: int | None = None) -> int | None:
    """Map a motif 1..5 tension to the outline 0..100 scale. None when neither the
    beat tension nor the motif-level fallback is present → the scene gets the A3
    neutral default (50) downstream, exactly as a model-omitted tension does
    (parse_scenes: 'neutral default 50'). fallback is motif.tension_target (also 1..5)."""
    v = tens5 if isinstance(tens5, int) and not isinstance(tens5, bool) else fallback
    if not isinstance(v, int) or isinstance(v, bool):
        return None
    return _MOTIF_TENSION_MAP.get(max(1, min(5, v)))
```

The map is the **single source of truth** for the cross-scale conversion; nothing else in W2 (or the codebase) hand-rolls a 1-5→0-100 formula. `adaptive_k` itself is **unchanged in signature** — `scenes_from_motif` (§2.5) does the conversion *before* calling `adaptive_k(beat_role, tension_0_100, ...)`, so the bound path and the invent path feed `adaptive_k` the same 0..100 contract. This is the cleanest reconcile: convert at the boundary, leave the gate untouched.

### §3.3 Does a bound motif overwrite scene tension? (→ K, → generate cost)

**Yes — a bound motif's beat tension becomes the scene's `tension`** (it replaces the model-invented value, because on the bind path there IS no model-invented value — scenes come from beats, §2.5). Consequences, traced:

1. **→ K (diverge candidate count):** the reconciled 0..100 tension flows into `adaptive_k` → `suggested_k` per scene, identical mechanism to invent. A motif "climax" beat (`tension_target=5` → 90) earns ceiling K; a "setup" beat (`2` → 30) earns K=1. **This is correct and intended** — the motif now *drives* the diverge budget, which is exactly the control surface the spec wants (§16.4: "the planner sets defaults, beat-derived, like adaptive-K already keys K on tension").
2. **The chapter-intent tension** (`_chapter_intent_tension`, §2.2) used to *select* a motif is a **coarse proxy** (derived from beat_role weight) and is **discarded after selection** — it never reaches a scene. Only the bound motif's per-beat tensions become scene tensions. No double-counting.

```python
def _chapter_intent_tension(beat_role: str | None, high_threshold: int) -> int | None:
    """A coarse chapter-level tension to feed retrieve()'s tension arg, derived from
    the beat_role weight (we have no per-scene tension yet). HIGH_WEIGHT_BEATS → high
    (clears the gate so retrieve prefers high-tension motifs); else mid. None when
    no beat_role (but selection is gated on beat_role anyway, §2.1)."""
    if beat_role is None:
        return None
    return high_threshold + 15 if beat_role.strip().lower() in HIGH_WEIGHT_BEATS else high_threshold // 2
```

### §3.4 Re-estimate cost AFTER binding, BEFORE the W-tier confirm

The audit (R3) wants the generate-cost estimate recomputed after binding, because binding *changes the K distribution* (and therefore the token spend of a subsequent `/generate auto`). W2's responsibility is to **expose the post-bind K distribution** so the confirm card is honest; it does **not** itself run the billing pre-check (that's the actions-router effect, W4-owned).

- **`motif_select.py` exposes** a pure helper:
  ```python
  def estimate_diverge_budget(chapters: list[ChapterScenes]) -> dict:
      """Σ suggested_k over all scenes (the diverge candidate count = the cost driver),
      split bound vs invented, so the generate confirm card reflects the POST-BIND K.
      Returns {total_k, bound_k, invent_k, scene_count}. Pure — no I/O."""
  ```
- The decompose **preview response** carries this aggregate (§2 / routers/plan.py preview fields). When the author then triggers a cost-gated `/generate auto` over the planned chapters, the **existing** `composition.generate` confirm path (`routers/actions.py:_GENERATE_DESCRIPTOR`) reads the persisted scenes' `suggested_k` and runs its usage-billing pre-check on the **post-bind** numbers — because the scenes were written with the motif-driven tension. **No new confirm descriptor is needed for the plan step itself** (planning is not a token spend; only generate is). W2's job is to make sure the persisted `tension`/`suggested_k` are the reconciled motif values, which they are by §3.2–§3.3. This satisfies R3 without W2 reaching into billing.

> **Why this is the right seam:** the plan step (decompose) is free (no LLM on the bind path; the invent path's LLM cost is unchanged). The *spend* is downstream generate, which already has a confirm + pre-check. By making the planner write motif-reconciled tension/K, the existing generate confirm is automatically post-bind-accurate. W2 adds the `estimate_diverge_budget` aggregate to the preview purely for author visibility ("this plan will cost ~N candidates"), not as a new gate.

---

## §4 Swap-motif-after-generation (§R2.6 / audit H-4)

### §4.1 The lifecycle (spec §R2.6 verbatim, made concrete)

Swapping a chapter's bound motif **after scenes already have prose** must **archive (never delete)** the affected scene nodes + their `generation_job` links, instantiate the new motif's scenes, flag orphaned `narrative_thread` promises for author review (never auto-close), and **undo = restore** the archived nodes. This honors the Tier-A `composition_motif_bind` undo hint (clears MCP-R2's "unhonored undo" finding).

The endpoint is the §5/§11 ★ `PATCH /v1/composition/works/{project}/outline/{node}/motif` (the single biggest A3 miss — the preview was read-only). `{node}` is the **chapter** outline_node.

### §4.2 The exact control flow (grounded in the REAL archive/restore)

`outline.py:archive_node` (line 635) soft-archives a node **and its whole descendant subtree** (it walks `parent_id` DOWN *from* the target — so passing the chapter node would archive the chapter too). `restore_node` (line 669) is its exact inverse (un-archives subtree + ancestor chain). `generation_job.outline_node_id` is FK **`ON DELETE SET NULL`** (`migrate.py:226`) — but we **never delete**, so the prose job rows survive intact and stay linked to the (now archived) scene nodes. This is *why* archive-not-delete works for undo: the prose is still attached.

> **Scenes-only archive — use the REAL replace-path precedent, NOT `archive_node(chapter_id)`.** We want to archive the chapter's **scenes** while **keeping the chapter node** (the motif rebinds onto the same chapter). The codebase already does exactly this in `commit_decomposed_tree`'s `replace` branch (`outline.py:374-382`): a **direct** `UPDATE outline_node SET is_archived=true WHERE user_id=$1 AND project_id=$2 AND chapter_id=ANY($3) AND kind='scene' AND NOT is_archived`. W2 reuses that shape (a F0/W2-exposed `outline.archive_chapter_scenes(user_id, project_id, chapter_id, conn=…)` helper, or the inline UPDATE on the open Tx connection) — **not** `archive_node(chapter_node_id)` (which would archive the chapter). Undo restores via the symmetric `kind='scene' AND chapter_id=…` flip (the scenes' `generation_job` rows are still attached, since we never deleted).

```python
# the swap effect (engine/motif_select.py provides plan_swap/apply_swap; routers/plan.py wires the endpoint)

async def apply_motif_swap(
    outline: OutlineRepo, applications: MotifApplicationRepo, threads: NarrativeThreadRepo,
    user_id: UUID, project_id: UUID, chapter_node_id: UUID, *,
    new_motif: SelectedMotif | None, binding: MotifBinding | None,
    cast_index: dict[str, str], conn: asyncpg.Connection,
) -> SwapResult:
    """ONE transaction:
      1. PROJECT-SCOPE the chapter node (get_node → assert project_id) — IDOR guard,
         the SAME pattern mcp/server.py uses before archive_node (lines 483-489).
      2. ARCHIVE the chapter's current SCENES (keep the chapter node) via the
         replace-path UPDATE (kind='scene' AND chapter_id=…; §4.2 note). Capture the
         archived scene ids FIRST (for undo + orphan-thread detection). The scenes'
         generation_job rows are UNTOUCHED (no delete) → prose preserved, restorable.
      3. RECORD the swap in the prior application row (mark superseded, keep history —
         motif_application is append-only history; the old row stays, flagged).
      4. INSTANTIATE the new motif's scenes (scenes_from_motif) as FRESH scene nodes
         under the chapter (create_node, kind='scene', parent=chapter_node), with the
         new role_bindings; write the new motif_application row.
      5. FLAG orphaned narrative_thread promises — any open thread whose promise scene
         is in the archived set is SURFACED for author review (never auto-closed, §R2.6).
      6. Return SwapResult{archived_scene_ids, new_scene_ids, orphaned_thread_ids,
         undo_token} — undo_token bundles {chapter_node_id, archived_scene_ids,
         new_scene_ids, prior_application_id} so undo (§4.3) is exact + idempotent."""
    target = await outline.get_node(user_id, chapter_node_id, conn=conn)
    if target is None or target.project_id != project_id or target.kind != "chapter":
        raise uniform_not_accessible()                          # H13 — no enumeration oracle

    archived_ids = await outline.archive_chapter_scenes(            # the replace-path UPDATE shape
        user_id, project_id, target.chapter_id, conn=conn)         # keeps the chapter node; archives its scenes
    ...
```

**Clear-motif (swap to nothing)** is the same flow with `new_motif=None`: archive the scenes, flag orphaned threads, write **no** new scenes (the chapter reverts to unplanned), mark the application superseded. The author can then re-decompose or hand-author.

### §4.3 Undo = restore (the honored Tier-A undo)

```python
async def undo_motif_swap(outline, applications, user_id, project_id, undo_token, conn):
    """Inverse of apply_motif_swap (the _meta.undo_hint the A-tier _bind tool returns).
    undo_token = {chapter_node_id, archived_scene_ids, new_scene_ids, prior_application_id}:
      1. ARCHIVE the swap's new scene nodes (new_scene_ids — they were freshly created).
      2. RESTORE the previously-archived scenes (un-archive archived_scene_ids — re-
         attaches the scenes AND their still-linked generation_job prose, never deleted).
         Restore by id-set (symmetric with step-2-of-apply), not restore_node's ancestor
         walk, since the chapter node was never archived (only its scenes were).
      3. Restore the prior motif_application row to active; archive the new one.
    Net effect: the chapter is back to its pre-swap motif + prose, exactly."""
```

Because `generation_job` rows were never deleted (only their scene nodes archived), un-archiving the scene id-set brings back the **prose-bearing** scenes intact — the undo is lossless. This is the precise mechanism that makes the §13.1 `composition_motif_bind` `undo_hint = restore prior binding` *real* (the audit's MCP-R2 finding was that the undo was advertised but not implemented; W2 implements it here, and W4 wires the MCP tool to call `undo_motif_swap`).

### §4.4 The W2↔W4 seam (bind engine vs MCP envelope)

- **W2 owns the bind/swap/undo ENGINE** in `motif_select.py`: `bind_motif`, `apply_motif_swap`, `undo_motif_swap`, `plan_swap` (the read-only preview of what a swap would archive/create, for the confirm/undo UX).
- **W4 owns the MCP TOOL** `composition_motif_bind` in `mcp/server.py`: it builds the tool context (envelope identity), gates (`require_book_owner` EDIT), project-scopes, then **calls W2's `apply_motif_swap`** and returns `_meta.undo_hint` pointing at `undo_motif_swap`. W4 does not re-implement bind logic; it adapts the envelope to W2's engine.
- **routers/plan.py (W2)** owns the **HTTP** `PATCH …/motif` endpoint: same engine call, JWT-gated, for the non-agentic form-driven swap (§13.3 HTTP line). One engine, two entries (MCP + HTTP), mirroring the §13.3 "one retrieval core, two entries" principle.

This keeps file ownership disjoint (master rule): W2 never edits `mcp/server.py` (W4's), W4 never edits `motif_select.py` (W2's). The seam is the function signatures of `apply_motif_swap`/`undo_motif_swap`, which W2 freezes in `motif_select.py` and W4 imports.

---

## §5 Tie-break for top-1 (reproducibility) + status filter

### §5.1 The deterministic tie-break (master §4 W2 eval-gate: "reproducible top-1")

`retrieve()` returns candidates sorted by `score` (cosine) desc. **Floating-point cosine ties are common** when two motifs have near-identical summaries (e.g. a system motif and its user clone). An undeterministic top-1 makes the planner non-reproducible (the eval-gate needs a stable result; the author needs "the same plan twice"). W2 applies a **total order**:

```python
def _pick_top1(cands: list[MotifCandidate]) -> MotifCandidate:
    """Deterministic top-1 over the retrieve()-ranked list. Primary = score (already
    sorted). Tie-break, in order (audit reproducibility, master §4 W2):
      1. score            desc   (the cosine rank from W3)
      2. mining_support   desc   (a mined motif proven across more books is preferred)
      3. judge_score      desc   (higher graded quality wins)
      4. code             asc    (the final, ALWAYS-unique deterministic key — code is
                                  unique per tier; stable across runs and machines)
    code is the backstop that guarantees a total order even when score/support/judge
    all tie (a clone shares its source's content) — never rely on list/DB order."""
    return min(cands, key=lambda c: (
        -c.score,
        -(c.motif.mining_support or 0),
        -float(c.motif.judge_score or 0),
        c.motif.code,
    ))
```

`code` is the tie-break backstop precisely because it is **unique within a tier** (`uq_motif_user (owner,code,language)` / `uq_motif_system (code,language)`, §R1.4) and **stable** (it's the cross-tier identity key, not a random uuid). Two candidates can tie on score+support+judge (a clone copies content) but never on code. This gives a provably total order — the reproducibility guarantee.

### §5.2 `status='active'` filter in retrieve consumption

W3's `retrieve()` already filters `status='active'` in SQL (§1.2 obligation 1) — **drafts and archived motifs never reach the planner**. W2 **relies on** this and does not re-filter (no drift). The rationale chain: a `status='draft'` motif (a mined/imported candidate awaiting author review, §3.5/§11) must NOT auto-bind into a plan — it isn't promoted yet. The planner only ever sees `active`. (The MCP `_search` tool, W4, separately gains a `status?` arg to *surface* drafts for the author's review queue — but that's a discovery path, not the planner's bind path. W2's planner is `active`-only, full stop.)

> **W2 unit test asserts this as a guard** even though W3 enforces it: the `FakeRetriever` is fed a mixed list including a draft, and the test asserts the planner never binds it — catching a future W3 regression at the W2 boundary (defense-in-depth, master §7).

---

## §6 The eval-gate `scripts/eval_motif_planner.py` (master §4 W2)

### §6.1 The 3-way comparison (audit AI-quality)

Mirrors `scripts/eval_a3_decompose.py` (same premise + book + disjoint judge), but runs **three** arms on the **same labeled seed**:

| Arm | What | Why |
|---|---|---|
| **A. motif-planner** | decompose with `motifs_enabled=True` (select+bind) | the thing we're shipping |
| **B. A3-invent** | decompose with `motifs_enabled=False` (today's planner) | the baseline — proves non-regression |
| **C. A3-invent + plot-nudge** | A3 invent with a prompt addendum that *tells* the model to weight plot ("ensure each scene carries a concrete plot event, not filler") | **the honest control** — isolates whether the win is the *library* or just *asking for plot*. If C ≈ A, the motif machinery isn't earning its complexity; if A > C, the structured library beats a prompt nudge (the research's prediction) |

The 3-way is the audit's demand (master §4 W2): without arm C, a motif win could be a confound (any plot-focused prompt would help). Arm C falsifies that.

### §6.2 Primary metric = plot-density on the labeled seed

- **Primary: `plot_density`** — the discriminating dimension the research ("Style over Story", arXiv:2510.02025) predicts the motif fixes: does each scene carry an *actual plot event* (a reversal, a revelation, a consequential action) vs filler/mood. Scored by a disjoint LLM judge on the **labeled seed** (the ~25-50 PO-labeled scenes, R2.1 — shared with W5's conformance calibration; W2 consumes the same seed, does not own labeling).
- **Report format** (mirrors `eval_a3_decompose`): per-arm median + distribution of plot-density; per-arm coherence-median + outline-relevance (the existing A3 dims, to prove non-inferiority); wall-clock + Σ-K spend per arm (the motif arm should be *cheaper* on the plan step — no L2 LLM on bound chapters).
- **Ship gate (spec §6, §10):** **A ≥ B on plot-density** AND **A coherence-median non-inferior to B** (motifs must not *hurt* coherence to help plot). The honest-finding stance (spec §6): if A beats B on plot-density but not coherence-median, **report that** — plot-density is the signal the research predicts, coherence parity is the floor.

### §6.3 Fallback-path non-regression (the second gate)

A separate eval mode forces the **no-match path**: run arm A against a book whose genre has **no seed motifs** (so every chapter falls back to invent). Assert arm A's output is **identical-in-distribution to arm B** (coherence + plot-density within noise) — proving the fallback is a true no-op, not a degradation. This is the executable form of acceptance #4 (§10: "no-match falls back, no regression") and master §7's fallback guard. Implementation: seed-pack-absent run → assert `all(cs.motif is None for cs in result.chapters)` AND the metric deltas vs arm B are within the judge's noise band.

### §6.4 Reproducibility assertion

The eval runs arm A **twice** with a fixed seed and asserts the bound motif_ids are **identical** across runs (the §5 tie-break guarantee) — catching any non-determinism in selection before it pollutes the metric comparison.

---

## §7 Tests + audit risk-guards

`tests/unit/test_motif_select.py` (W2-owned), each audit guard as a **failing-test-first** row (master §7):

### §7.1 Core select/bind/scenes
- `retrieve` returns 1 candidate, score≥floor, full bind → chapter is bound; `ChapterScenes.motif` set; scenes == motif beats (count, order, titles); `motif_application` payload has `motif_id`+`motif_version`+`role_bindings`.
- Top-N → top-1 selection picks the highest-score candidate.
- `scenes_from_motif` clamps to `max_scenes`; under-fill (beats < min_scenes) does NOT pad.
- `_render_beat_synopsis` substitutes bound names; leaves unbound role keys abstract.

### §7.2 The F1 fallback matrix (audit F1) — one test per cell
- mapped × empty → invent, `warning='no_motif_match'`, `motif is None`.
- mapped × errored (`FakeRetriever` raises) → invent, `warning='motif_retrieve_degraded'`.
- mapped × candidates-below-floor → invent, `warning='motif_below_floor'`.
- mapped × candidates × partial-bind → **bound** (not fallback), `warning='partial_role_bind'`, `unresolved_roles` surfaced.
- degraded-L1 (`beat_role=None`) × candidates → **never retrieves** (gate asserts `retrieve` not called), invent.
- connective beat × weak candidate → invent (higher floor); connective × strong candidate → bound.

### §7.3 Tension reconcile (audit R3)
- `motif_tension_to_scale(5)==90`, `(4)==75`, `(3)==50`, `(2)==30`, `(1)==10`; `(None, fallback=4)==75`; `(None, None) is None`.
- A bound climax beat (`tension_target=5`) → scene tension 90 → `adaptive_k` returns ceiling K (regression-locks the reconcile→K path).
- A bound setup beat (`2`) → tension 30 → K=1.
- `estimate_diverge_budget` sums bound+invent K correctly; the preview carries it.

### §7.4 Swap (audit H-4)
- `apply_motif_swap` archives the chapter's **scenes** (assert `is_archived`) while the **chapter node stays active** (assert `kind='chapter'` row NOT archived), and does **NOT** delete `generation_job` rows (assert the job rows still exist + still reference the archived scene ids).
- Swap instantiates the new motif's scenes + writes a new `motif_application`; the old application row is retained (history), marked superseded.
- `undo_motif_swap` un-archives the prior scene id-set + re-attaches their prose jobs + archives the new scenes → chapter byte-identical to pre-swap.
- IDOR: a chapter node from another project → `uniform_not_accessible` (the `get_node`→`project_id` assert, mirrors `mcp/server.py:487`).
- Orphaned `narrative_thread` promise on an archived scene is **surfaced** in `SwapResult.orphaned_thread_ids`, **not auto-closed** (assert the thread row is untouched).

### §7.5 Reproducibility + status (master §4 / §5)
- `_pick_top1` total-order: two candidates tied on score+support+judge but different `code` → the lower `code` wins, deterministically across repeated calls.
- B1 telemetry / anti-repetition: the planner emits a **coverage signal** "N of M chapters bound" (§7.6) — assert it counts bound vs total mapped chapters.
- status guard: a `status='draft'` candidate in the `FakeRetriever` list is **never bound** (defense-in-depth over W3's SQL filter).

### §7.6 B1 coverage telemetry ("N of M chapters bound")

The audit (B1) wants the planner to **report bind coverage**, not silently bind some and invent others. `DecomposeResult` gains a `motif_coverage` field:

```python
@dataclass
class DecomposeResult:
    arc_title: str
    chapters: list[ChapterScenes] = field(default_factory=list)
    unmapped_beats: list[str] = field(default_factory=list)
    motif_coverage: dict = field(default_factory=dict)
    #   {"mapped_chapters": M, "bound_chapters": N, "distinct_motifs": k,
    #    "fallbacks": {"no_motif_match": .., "motif_retrieve_degraded": .., "motif_below_floor": ..}}
```

This surfaces in the preview ("bound a motif to N of M chapters") so the author knows the library's reach on this book, and the eval-gate can assert coverage. The **anti-repetition** signal (`motif_max_reapply`, §11/§16) reads `motif_application(book_id, motif_id)` (the `idx_motif_application_book_motif` index, §R1.4) at select time: if a motif is already applied ≥ `motif_max_reapply` times in the book, it is **deprioritized** (dropped below the floor) so the same trope doesn't carpet the book — the cowrite craft-nudge made structural (spec §2.3, §9 risk 2). W2 reads this count via a F0-exposed `applications.count_for_book(book_id, motif_id)`; the deprioritization happens in `select_motif_for_chapter` after `_pick_top1`.

---

## §8 Open micro-decisions + recommendation

| # | Decision | Options | **Recommendation** |
|---|---|---|---|
| **MD-1** | Bind anchor: chapter node vs each scene node | (a) one application per chapter (role_bindings propagate to scenes); (b) one per scene | **(a) chapter** — matches the swap unit, the §R1.4 single `outline_node_id`, and keeps anti-repetition = "distinct motif per book" clean. Per-scene attribution is W5's `scene_span` job, not W2's. |
| **MD-2** | Role→cast binding heuristic | (a) name-hint via `_resolve_cast` on `label`+`constraints`; (b) an LLM bind call; (c) actant-type matching | **(a) name-hint, no LLM** — keeps the bind path LLM-free (the latency/cost win) and reuses the proven resolver. Unbound roles surface for the author (the §11 cast-picker). An LLM bind is a P2+ enhancement if hint-matching proves too weak on the seed. |
| **MD-3** | `_CONNECTIVE_FLOOR` value | tune | **`motif_min_score + 0.08`**, exposed as `config.motif_connective_floor_margin` so it's tunable at eval without a code change. |
| **MD-4** | Motif tension map anchors | linear `{20,40,60,80,100}` vs the band-aligned `{10,30,50,75,90}` | **band-aligned `{10,30,50,75,90}`** — deliberately puts 4 and 5 *both* above the 70 high gate (a motif's turn/climax beats should earn ceiling K) and 3 squarely mid-band. Pure-linear would put `4→80` fine but `3→60` also mid — acceptable, but the chosen anchors are more intentional about the gate. |
| **MD-5** | When to write `motif_application` | preview (eager) vs commit (lazy) | **commit (lazy)** — preview is non-persisted (A3 invariant); writing applications at preview would orphan rows the author never commits. The preview *carries* the payload for display; commit persists it in the tree Tx. |
| **MD-6** | Swap on an un-generated chapter (no prose yet) | archive+reinstantiate vs in-place re-derive | **archive+reinstantiate uniformly** — one code path regardless of prose state (archive_node no-ops cleanly on scenes with no jobs). Simpler + the undo works identically. An "in-place" optimization for the no-prose case is a premature special-case. |
| **MD-7** | Motifs default ON or OFF in `decompose_preview` | flag default | **default OFF in P1 ship, flip ON after the eval-gate passes** — a `motifs_enabled` request flag (+ `config.motif_planner_default`) so the eval-gate compares arms cleanly and we don't change A3's default behavior until A≥B is proven. (Spec §10 acceptance is gated on the eval; shipping ON before the gate is the anti-pattern.) |

---

## §9 Task list (build order, TDD)

> Size: this WS is **L** (7-12 logic units: select, bind, scenes-from-beats, tension-reconcile, fallback-matrix, swap, undo, tie-break, coverage-telemetry, eval-3-way; side effects: the swap endpoint + the `motif_application` write are DB/API → risk floor met). Plan file = this doc. Build against the F0 frozen `retrieve()`/`Motif`/`MotifApplication` signatures with the `FakeRetriever` mock.

1. **T0 — scaffold + mock.** `engine/motif_select.py` skeleton (dataclasses `SelectedMotif`/`MotifBinding`/`SwapResult`); `FakeRetriever` + `MotifCandidate`/`Motif` fixtures in the test file. Import the frozen F0 models. (Compiles green against F0 stubs.)
2. **T1 — tension reconcile (`adaptive_k.py`).** Add `_MOTIF_TENSION_MAP`, `motif_tension_to_scale`, `_chapter_intent_tension`. Tests §7.3. *(Isolated, no retrieve dep — do first; it unblocks scenes-from-motif.)*
3. **T2 — select.** `select_motif_for_chapter` + `_pick_top1` (tie-break §5) + the connective-floor + the status guard. Tests §7.1 (top-1), §7.5 (tie-break, status).
4. **T3 — bind + scenes.** `bind_motif` (reuse `_resolve_cast`), `_bind_annotations`, `scenes_from_motif`, `_render_beat_synopsis`, `build_application_row`. Tests §7.1.
5. **T4 — the L2 splice (`plan.py`).** Thread `motifs_enabled` + book genres/language/`caller_id` through `decompose`; rework `one_chapter` per §2.1; extend `ChapterScenes`/`DecomposeResult` (motif/binding/application/coverage). The full F1 fallback matrix. Tests §7.2, §7.6.
6. **T5 — cost aggregate.** `estimate_diverge_budget`; carry it + `motif_coverage` in the preview. Test §7.3 (budget).
7. **T6 — swap engine.** `apply_motif_swap`, `undo_motif_swap`, `plan_swap` (grounded in `archive_node`/`restore_node`/`get_node`). Tests §7.4 (incl. IDOR + orphan-thread + prose-preservation + lossless undo).
8. **T7 — routers/plan.py wiring.** `decompose_preview` passes the toggle + genres/language; `decompose_commit` persists `motif_application` rows in the tree Tx (call F0's `applications.insert_many`); add the `PATCH …/outline/{node}/motif` endpoint (JWT-gated, calls `apply_motif_swap`/`undo_motif_swap`). Preview DTOs gain the motif fields.
9. **T8 — eval-gate.** `scripts/eval_motif_planner.py`: the 3-way (A/B/C), plot-density primary, fallback-non-regression mode, reproducibility assertion. (Consumes the R2.1 labeled seed — coordinate with W5; do NOT own labeling.)
10. **T9 — VERIFY.** Full `test_motif_select.py` green; `eval_motif_planner.py` runs (against the FakeRetriever in CI, against W3 at R-NODE-P1). Live-smoke deferred to **R-NODE-P1** (master §6) — token: `LIVE-SMOKE deferred to R-NODE-P1` (W3's real retrieve + a seed pack are needed; not bootable from W2 alone). The cross-service seam (composition planner ↔ W3 retrieve ↔ W5 conformance) is exercised there.

### Contract test (the W2↔F0 + W2↔W3 boundary)
`tests/contracts/` (F0-owned, W2 contributes a row): assert `motif_select.select_motif_for_chapter` calls `retriever.retrieve` with **exactly** the frozen kwargs (`book_id/project_id/genre_tags/language/beat_role/tension/prev_effects`) — so when W3's real impl lands, the call site matches the frozen signature with zero adaptation. This is the "integration = contract test, not big-bang" guarantee (master §1).
