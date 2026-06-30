# Story 03 — Self-heal / Polish (the double-edged quality pass)

> Status: 🟡 **discussing**. Backend engine already built (`services/composition-service/app/engine/self_heal.py`);
> this story is the **UX/UI** for exposing it. Evidence: [`../../2026-06-30-chapter-synthesis-self-healing.md`](../../2026-06-30-chapter-synthesis-self-healing.md)
> §"Cheap quality stack", and the CH1–12 drive in [`../story-export-v2/`](../story-export-v2/) + [`../poc/io/heal_v2_summary.json`](../poc/io/heal_v2_summary.json).

## Context — why this is a *feature*, not an always-on step

The compose pipeline can run a multi-pass self-heal: **grounded LLM judge → vote → skeptical verify →
satellite-edit → splice → re-judge**. Validated on the Lâm Uyển POC on a **$0 local model**: it fixed
xưng-hô / canon / dup-word errors **book-wide** with **no inflation** (x0.998–1.005), and the win came
from architecture (grounding + discipline), not model size.

**But it is a double-edged sword (PO, 2026-07-01):**
- The **deterministic layers** (modern-pronoun + lexical prefilter) are reliable — near-100% on closed
  classes (0 real pronoun residuals across all 12 chapters).
- The **semantic verify layer is stochastic + fail-toward-refute** → it occasionally **drops a real
  finding** (CH01 `mẫu thân ngươi` regressed vs the dedicated run; CH03 refuted 5/5), and a judge/editor
  can still mis-edit. So an always-on, silently-applied heal can **both miss fixes and (rarely) touch
  good prose**.

⇒ **It MUST be user-controlled and never a silent rewrite** — manual or auto activation, always behind a
human review-gate. The cheap stack's job is "fewest errors, then human / stronger-model gate" — the UI
*is* that gate.

## User story

- **C5.** As an author, I want to **trigger a Polish pass on demand** (manual) on the open chapter or
  scene — and optionally **enable auto-polish** after a draft/generate — and in **both** cases **review
  every proposed edit (accept / reject) before it touches my prose**, so an imperfect-but-cheap pass
  never silently changes my text.

## Locked design decisions

1. **Two activation modes.**
   - **Manual** (default): a *Polish / Heal* action in the **Quality** group (and a quick action on a
     just-generated draft) runs the pass on the current unit.
   - **Auto** (opt-in, off by default): run the pass automatically right after a scene/chapter draft
     completes. Per-book preference, **server-synced** (server is SSOT — not localStorage).
2. **Always a review-gate, never silent-apply.** The pass returns **proposals** (the `SelfHealReport`
   findings + each satellite edit as a span diff), shown as an **accept/reject diff list** (PR-review
   style): per edit show `type`, the quoted span, the issue, and before→after. Only accepted edits
   splice in. **Deterministic prefilter edits default-checked** (high confidence); **semantic edits
   default-unchecked but visible** (because verify is imperfect). "Accept all deterministic" /
   "Reject all" bulk actions.
3. **Per-run controls (advanced, sensible defaults).** grounding/canon = **always on** (sourced from the
   book's cast bible / planning `PipelineResult`); `verify` on/off + strictness; **vote depth** (cheap 1 /
   standard 3 / thorough 5); `prefilter` on/off. A small *Polish settings* popover; defaults = grounded +
   vote 5 + verify on + prefilter on. Show heal stats (×len ratio, N findings, M refuted) for transparency.
4. **Stronger-model escalation hook (cost-gated).** Optionally send the post-cheap-stack survivors to a
   stronger model for the final semantic gate — the human can also be that gate. Resolves the verify
   recall gap (#2) for users willing to pay.
5. **Scope = chapter or scene.** Manual pass operates on whichever unit is open; satellite edits stay
   span-local (sentence-snapped).

## UX surface

- **Quality group → new `polish` panel** (see [`../02_DESIGN.md`](../02_DESIGN.md) panel→group map).
- **Diff/review pane**: proposed-edit list with per-edit accept/reject, bulk actions, and the heal-stats
  header.
- **Auto-polish toggle** in Compose/Quality settings (per-book, server-synced).

## Backend status (already built — UI is the gap)

`engine/self_heal.py` exposes the full stack via params (`canon`, `vote_k`, `min_votes`, `verify`,
`prefilter`) — all **default-OFF** (legacy byte-identical). **Remaining BE task:** per the **MCP-first
invariant**, the agentic heal must be exposed as an **MCP tool on composition-service** following the
**propose→confirm** pattern — it returns *proposals* for the review-gate, never a silent write. Canon
should be wired from the planning pipeline's `PipelineResult` cast bible.

## Open questions for PO

- Auto-polish default: **off** (proposed) vs **on-for-deterministic-edits-only**?
- Accepted edits → **new draft version (OCC)** or **edit-in-place with undo**?
- Stronger-model escalation: which capability/model + cost-gate UX (mirror the compose confirm-token cost gate)?
