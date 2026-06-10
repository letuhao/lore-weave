# A2-S4a — co-write FE canon panel + Revise affordance (PLAN)

> Track: LOOM · Milestone: A2-S4a (first half of A2-S4, split per PO) · Size: **L** · 2026-06-06
> Default v2.2 human-in-loop. FE-only; consumes already-shipped backend fields (A2-S3b).

## Goal
Surface the auto `/generate` `canon` block (`violations` + `resolved` + `status`) in the compose
surface, distinguishing **hard** (confirmed contradiction) vs **advisory** (symbolic-only, unverified)
vs **unchecked** (canon protection didn't apply), and give the author a **Revise** affordance that
pre-fills the guide textarea with the violation context + focuses it (author steers, PO decision).

A2-S4b (publish-gate canon distinction in the editor toolbar) is a **separate** sub-session.

## Backend contract (already live — DO NOT change)
- `engine.py` auto path returns `canon: { violations[], resolved, iterations, status }`
  ([engine.py:281-295](../../services/composition-service/app/routers/engine.py#L281-L295)).
- Each violation = `CanonViolation` ([canon_check.py:60-70](../../services/composition-service/app/engine/canon_check.py#L60))
  with `confirmed: true|false|null`. The BE already **excludes** judge-cleared (`confirmed=false`);
  the FE only sees `true` (hard) / `null` (advisory) but filters defensively.
- `status ∈ {checked, skipped_no_cast, skipped_no_position, degraded}`.
- The auto **replay** branch ([engine.py:211-216](../../services/composition-service/app/routers/engine.py#L211)) omits `canon` → FE guards on presence.

## Files
1. **`frontend/src/features/composition/types.ts`** — add `CanonViolation` + `CanonResult` types;
   add optional `canon?: CanonResult` to `AutoGeneration`.
2. **`frontend/src/features/composition/components/CanonGatePanel.tsx`** (new, pure view) —
   props `{ canon: CanonResult; onRevise: (v: CanonViolation) => void }`. Renders:
   - `status !== 'checked'` → **unchecked** banner (amber/neutral) + reason (no-cast / no-position / degraded).
   - `status === 'checked'`:
     - hard violations (`confirmed === true`) → **red** section, each row: name + why/span + `Revise`.
     - advisory violations (`confirmed == null`) → **amber** section, each row + `Revise`.
     - no violations → subtle **clear** line ("Canon: clear" + "auto-revised ×N" when iterations>0).
   - `data-testid` on panel + each section + each Revise button.
3. **`frontend/src/features/composition/components/ComposeView.tsx`** — add a `guideRef`
   (`useRef<HTMLTextAreaElement>`), render `<CanonGatePanel>` inside the existing
   `diverge && auto.data && !auto.isPending` block (above `CandidatesView`), guarded by `auto.data.canon`.
   `handleRevise(v)` builds a guidance line from the violation (`t('reviseGuide', {name})` + optional
   `why`), **appends** to existing `guide` (newline-sep if non-empty), then `guideRef.current?.focus()`.
4. **`frontend/src/i18n/locales/{en,ja,vi,zh-TW}/composition.json`** — new keys (mirror all 4):
   `canonClear, canonAutoRevised, canonHardTitle, canonAdvisoryTitle, canonUncheckedTitle,
    canonUncheckedNoCast, canonUncheckedNoPosition, canonUncheckedDegraded, revise, reviseGuide`.
   en authored; ja/vi/zh-TW translated (no English token bleed — these are UI chrome, not LLM prose).
5. **`frontend/src/features/composition/components/__tests__/CanonGatePanel.test.tsx`** (new) —
   render each state (clean / hard / advisory / unchecked×reasons); assert testids + that `onRevise`
   fires with the violation. Assert on violation data (`name`/`why`) + testids, NOT i18n strings
   (global react-i18next mock returns raw keys — feedback lesson).

## Non-goals (this sub-session)
- Publish-gate canon distinction (A2-S4b).
- Capturing a correction on Revise (Revise just steers the guide; existing Regenerate/Reject capture).
- Any backend / contract / gateway change.

## Verify
- `npm run test` (vitest) for the new CanonGatePanel test + the composition feature suite (no regression).
- `npx tsc --noEmit` clean.
- Cross-service live-smoke: **N/A — FE-only, consumes A2-S3b fields already live-proven**
  (`canon.status=skipped_no_position` confirmed on a real qwen2.5-32b run this arc). Token:
  `LIVE-SMOKE deferred to D-A2S3B-LIVE-SMOKE` (the gone-cast contradiction-FIRE scenario; tracked).

## Review focus (Phase 7)
- Spec: hard/advisory/unchecked all distinctly rendered; Revise pre-fills + focuses (PO decision).
- Quality: MVC (panel renders only); ComposeView <200 lines; no useEffect for the Revise action
  (direct callback); guard on `canon` absence (replay/cowrite); defensive `confirmed===false` filter.
