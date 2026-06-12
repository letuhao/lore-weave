# A2-S4b — publish-gate canon distinction in the editor toolbar (PLAN)

> Track: LOOM · Milestone: A2-S4b (second half of A2-S4) · Size: **L** · 2026-06-06
> Default v2.2 human-in-loop. FE-only; consumes already-shipped gate fields (A2-S3b / D-A2S3B-PUBLISH-GATE).

## Goal
The composition publish-gate already returns `canon_blocked` / `canon_unresolved_scenes` /
`canon_unchecked_scenes` ([outline.py:388-399](../../services/composition-service/app/db/repositories/outline.py#L388))
but the FE drops them. Surface:
- a **distinct canon-contradiction blocked reason** (vs the existing "scenes not yet done"),
  **combined** when both apply (PO decision);
- a **non-blocking amber "unchecked" warning chip** with the scene count (PO decision) — `can_publish`
  already ignores unchecked, so publish stays enabled.

## Backend contract (already live — DO NOT change)
- gate → `{ chapter_id, scenes_total, scenes_done, canon_blocked, canon_unresolved_scenes,
  canon_unchecked_scenes, can_publish }`; `can_publish = total>0 && done==total && !canon_blocked`.

## Files
1. **`frontend/src/features/composition/types.ts`** — add `canon_blocked`, `canon_unresolved_scenes`,
   `canon_unchecked_scenes` to `PublishGate`.
2. **`frontend/src/features/composition/hooks/usePublishGate.ts`** —
   - `ChapterPublishGate` += `canonBlocked` / `canonUnresolvedScenes` / `canonUncheckedScenes`
     (degrade-open defaults 0/false when no Work / loading / error).
   - export **pure** `publishGateMessages(gate, t) → { blockedReason?, uncheckedWarning? }`:
     - `uncheckedWarning = canonUncheckedScenes>0 ? t('publish.gate_unchecked',{count}) : undefined`
     - not blocked → `{ blockedReason: undefined, uncheckedWarning }`
     - `scenesTotal===0` → `gate_no_scenes`
     - else join with `'; '`: pending part (`gate_pending`) if `done<total` + canon part
       (`gate_canon_blocked`) if `canonBlocked`; empty join → `undefined` (degrade open).
3. **`frontend/src/pages/ChapterEditorPage.tsx`** — replace the inline reason derivation with
   `publishGateMessages(publishGate, t)`; render an amber chip (`data-testid=publish-canon-unchecked`,
   `AlertTriangle` icon, `title=publish.gate_unchecked_hint`) next to `<PublishControl>` when
   `uncheckedWarning` set. PublishControl contract unchanged (still `blockedReason`).
4. **`frontend/src/i18n/locales/{en,ja,vi,zh-TW}/editor.json`** — 3 new `publish.*` keys (mirror ×4):
   `gate_canon_blocked` ("an unresolved canon contradiction in {{count}} scene(s)"),
   `gate_unchecked` ("Canon unverified in {{count}} scene(s)"),
   `gate_unchecked_hint` (explainer: cast present but no resolved reading position; publish allowed).
5. **`frontend/src/features/composition/hooks/__tests__/usePublishGate.test.tsx`** — extend:
   hook surfaces the 3 canon fields; `publishGateMessages` cases — pending-only, canon-only,
   **combined**, no-scenes, unchecked-warning present/absent, not-blocked. Assert on key+count
   (global i18n mock echoes `{{count}}`).

## Non-goals
- The auto-generate canon panel (A2-S4a — DONE).
- Any backend / gate-logic change (`can_publish` semantics stay; unchecked stays non-blocking).

## Verify
- `npm test -- usePublishGate` (project-local vitest 2.1.9 — NOT npx, which pulls v4 w/o jsdom)
  + the composition suite for no-regression; `& .\node_modules\.bin\tsc --noEmit` clean.
- Cross-service live-smoke: **N/A — FE-only**, consumes gate fields proven at D-A2S3B-PUBLISH-GATE.
  Token: `LIVE-SMOKE deferred to D-A2S3B-LIVE-SMOKE`.

## Review focus (Phase 7)
- Spec: canon-blocked reason distinct + combined; unchecked is a WARNING (publish NOT disabled).
- Quality: degrade-open on all error/no-Work paths; helper pure (no t bound inside); no useEffect;
  chip a11y (title tooltip, not icon-only-without-text).
