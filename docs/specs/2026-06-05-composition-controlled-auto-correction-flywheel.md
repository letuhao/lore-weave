# Composition V1 — Controlled-Auto + Correction Flywheel (design)

> **Status:** DESIGN draft (LOOM, 2026-06-05). Extends [`2026-06-05-composition-v1-reasoning-engine.md`](2026-06-05-composition-v1-reasoning-engine.md) (the reasoning core) + reuses the **learning-service** correction/preference flywheel (the eval-track Q2/Q3 infra) + the composition outbox (M9 `scene_committed`). A1 `diverge→converge` is built.
> **Thesis (PO):** early-stage V1 should be **controlled auto, not autonomous** — generate (diverge→converge) → **human gate** (the author corrects/accepts) → **capture the correction** → feed learning-service. The human gate guarantees quality (nothing bad ships) AND collects the preference signal to improve the drafter + reranker. This **also solves the A1 eval-gate problem**: the auto-judge coherence metric saturates (5/5); **human corrections are the discriminating quality ground-truth** (which scenes get edited / regenerated / re-picked = where the AI is weak).

---

## §1 Why controlled-auto beats the §8.3 hard-gate autonomous loop (for now)
The reasoning-engine spec §8.3 sketches an *autonomous* loop with the critic as a hard gate. But (a) the critic can't yet be trusted as a gate (the eval saturates — §A1 finding), and (b) we have no preference data to tune the drafter/reranker. So **sequence it:** controlled-auto (human gate + capture) FIRST → accumulate corrections → use them to train the reranker/drafter + validate the critic → THEN graduate to autonomous where the now-trusted critic gates. Corrections are the bridge.

## §2 Correction taxonomy — the human gate IS the signal
Five post-generate actions, each a **preference signal** mapping to learning-service's existing gold-label triple shape (`preferred` / `non_preferred`, Q2 `get_gold_labels`):

| Action | Preference signal | Trains | Notes |
|---|---|---|---|
| **accept** (as-is) | winner ≻ {rejected K−1 candidates} | reranker (confirms) | implicit: the rerank was right |
| **accept-with-edit** | `edited` ≻ `winner` | **drafter** (prose-level) | the (winner→edited) diff = the richest signal |
| **pick-different** (candidate j) | `cand_j` ≻ `winner_i` | **reranker** (directly — the judge was wrong) | only possible because all K are shown (§4) |
| **regenerate-with-guidance** | `−winner` + the guidance | **drafter** (what was missing) | the next accept chains as `new ≻ old` |
| **reject / discard** | `−whole generation` (scene+grounding) | negative example | no `preferred` |

**Key:** `pick-different` is a direct correction on the **reranker I built in A1** — closing the loop on the exact component whose quality the auto-eval couldn't measure.

## §3 Data model + flow (reuse, don't rebuild)

```
FE correction surface
   │  POST /v1/composition/jobs/{job_id}/correction {kind, chosen_candidate_index?,
   │                                                 guidance?, edited_text?}
   ▼
composition-service
   • generation_correction (NEW, per-work): {id, job_id, work_id, user_id, kind,
        chosen_candidate_index?, guidance?, edit_struct (diff: # changed blocks),
        raw_before?/raw_after? (OPT-IN only, §5), created_at}
   • emit `composition.generation_corrected` → outbox_events (reuse M9 emit pattern)
   ▼  relay (worker-infra, existing) → loreweave:events:composition
learning-service  (NEW consumer handler — the only learning-side code)
   • handle_generation_corrected → persist_consumed_score / a preference row:
        {source=composition, kind, preferred?, non_preferred?, change_magnitude,
         work_id, job_id, origin_event_id (dedup)}  ← mirrors Q2 corrections-as-gold
```

- **Composition** owns the capture + outbox (reuses M1 `outbox_events` + the M9 `scene_committed` txn-local emit). **One new table + one endpoint + one event type.**
- **learning-service** adds `loreweave:events:composition` to its consumer STREAMS + one `handle_generation_corrected` handler → its existing corrections/quality store (redact/hash schema, dual-dedup on `origin_event_id`). **No new store** — extends the eval-track corrections model.
- **`generation_job`** already retains `candidates` + `winner_index` (A1) → the preference pairs are reconstructable from the job + the correction.

## §4 FE — correction surface (always show all K candidates)
Extend the V0 `ComposeView` (ghost/accept/regenerate/discard) into the gate. **PO: always show all K candidates in parallel** (like §8.2 "takes" — maximum transparency + the most `pick-different` signal):
- **K candidate cards** side-by-side (the winner badged) — the author reads + compares.
- **Per-candidate:** Accept · Edit-then-accept (inline, the editor already supports insert; the diff is captured) · "This one instead" (pick-different).
- **Regenerate-with-guidance** (a guidance box + regenerate — reuses the V0 control; the guidance is captured).
- **Reject all.**
- Each action → `POST …/correction` with the kind. Accept also inserts to the editor (V0 SC4: ghost never autosaved until accept — preserved).
- Cost note: K parallel drafts already paid at generate; showing them is free. Reading 3 is the author's cost — acceptable for the quality gate + they chose it.

## §5 Raw-prose policy — OPT-IN (mirror `save_raw_extraction`)
Default = **structural + content-hash only** (the no-raw-text / multi-device privacy rule + learning-service redact-by-default). A per-work (or per-user) **`capture_correction_prose` opt-in** flips it to store the actual `winner`/`edited`/`chosen` prose — needed for prose-level preference tuning (DPO, V2). Same pattern + governance as the eval-track's raw-extraction opt-in. The structural signal (which candidate, edit magnitude, regenerate, kind) is ALWAYS captured; only the verbatim prose is gated.

## §6 The eval-gate, fixed
Replace the saturating auto-judge median with **correction-derived quality metrics** (the ground-truth the auto-judge lacked):
- **accept-as-is rate** (↑ = drafter+reranker good) · **edit rate + edit magnitude** (↓ = good) · **pick-different rate** (↓ = reranker good) · **regenerate rate** (↓ = drafter good) · **reject rate** (↓).
- A-slice gate: does `diverge→converge` (A1) lower edit/regenerate/reject rate vs V0 single-draft, on real author corrections? **This is a discriminating, human-grounded metric** — not a ceiling-5 auto-judge. (Auto-judge stays as a cheap proxy; humans are the gate.)

## §7 Build plan (full loop) — proposed slices
1. **BE capture** — `generation_correction` table + migration · `POST /jobs/{id}/correction` · `composition.generation_corrected` outbox emit (reuse M9 txn-local pattern) · the opt-in flag. Tests + live-smoke (composition outbox row).
2. **learning consume** — add `loreweave:events:composition` to STREAMS + `handle_generation_corrected` → preference store (reuse Q2/Q3 persist + dedup). Tests + live-smoke (both DB halves, like Q3a).
3. **FE correction surface** — K-candidate cards + accept/edit/pick/regenerate/reject + capture calls + i18n. Tests + tsc.
4. **gateway** — `/v1/composition/*` catch-all already proxies (no gateway change); learning already proxied.
5. **eval** — swap the A1 eval-gate to correction-rate metrics (§6); becomes the standing quality dashboard.

Each slice = own VERIFY + COMMIT (cross-service at 1+2 → live-smoke token).

## §8 Open decisions (at PLAN)
1. **`generation_correction` placement** — new table vs columns on `generation_job` (a job can have multiple corrections over time → new table).
2. **Preference reconstruction** — store the full `(preferred, non_preferred)` pair at capture time, or store the raw action + reconstruct from the job's candidates in learning? (Capture-time pair is simpler + dedup-stable.)
3. **regenerate chaining** — link the regenerated job to the prior (a `parent_job_id`) so `new ≻ old` is reconstructable.
4. **What counts as `edit`** — any post-accept editor change to the inserted span, or only edits made before accept? (Before-accept is cleanly attributable; post-accept edits blend with normal writing.)
