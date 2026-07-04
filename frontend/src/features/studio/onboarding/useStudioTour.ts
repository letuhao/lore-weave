import { useCallback, useRef, useState } from 'react';
import { STUDIO_TOURS, type StudioTourId, type StudioTourStepDef } from './tours';

const ANCHOR_WAIT_MS = 4000;
const ANCHOR_POLL_MS = 150;

/** Polls for a live DOM node rather than assuming react-joyride's own internal target-search
 *  timing — needed because a step's anchor may not exist yet until its panel is opened (an
 *  async dockview mount), which joyride itself has no way to trigger. */
function waitForAnchor(selector: string, timeoutMs: number): Promise<boolean> {
  return new Promise((resolve) => {
    const start = Date.now();
    const tick = () => {
      if (document.querySelector(selector)) { resolve(true); return; }
      if (Date.now() - start >= timeoutMs) { resolve(false); return; }
      setTimeout(tick, ANCHOR_POLL_MS);
    };
    tick();
  });
}

/**
 * #19 G3/G10 — drives the `core` guided tour one step at a time. Fully controls sequencing
 * itself (rather than trusting react-joyride's internal Back/Next/target-search state machine)
 * so the two resilience rules the spec locks in are simple to reason about:
 *   (a) `onOpenPanel` fires before EVERY step, not just once — idempotent open-or-focus, so a
 *       user manually closing a panel mid-tour self-heals on the next step instead of breaking.
 *   (b) a step whose anchor never appears (stale/typo'd selector) is SKIPPED after a fixed
 *       timeout instead of hanging the tour forever.
 */
export function useStudioTour(onOpenPanel: (panelId: string) => void) {
  const [tourId, setTourId] = useState<StudioTourId | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [anchorReady, setAnchorReady] = useState(false);
  const runToken = useRef(0);

  const steps: StudioTourStepDef[] = tourId ? STUDIO_TOURS[tourId] : [];

  const goToStep = useCallback(async (index: number, activeSteps: StudioTourStepDef[]) => {
    const myToken = ++runToken.current;
    setAnchorReady(false);
    const def = activeSteps[index];
    if (!def) { setTourId(null); return; }
    if (def.panelId) onOpenPanel(def.panelId);
    const found = await waitForAnchor(def.target, ANCHOR_WAIT_MS);
    if (myToken !== runToken.current) return; // superseded by a later start/stop/goToStep call
    if (!found) {
      if (import.meta.env.DEV) {
        // eslint-disable-next-line no-console -- dev-only diagnostic for a stale/typo'd anchor
        console.warn(`[studio-tour] anchor not found within ${ANCHOR_WAIT_MS}ms, skipping step: ${def.target}`);
      }
      void goToStep(index + 1, activeSteps);
      return;
    }
    setStepIndex(index);
    setAnchorReady(true);
  }, [onOpenPanel]);

  const start = useCallback((id: StudioTourId) => {
    const activeSteps = STUDIO_TOURS[id];
    setTourId(id);
    void goToStep(0, activeSteps);
  }, [goToStep]);

  const stop = useCallback(() => {
    runToken.current += 1; // invalidate any in-flight wait
    setTourId(null);
    setAnchorReady(false);
  }, []);

  const next = useCallback(() => {
    if (stepIndex + 1 >= steps.length) { stop(); return; }
    void goToStep(stepIndex + 1, steps);
  }, [stepIndex, steps, goToStep, stop]);

  const prev = useCallback(() => {
    if (stepIndex <= 0) return;
    void goToStep(stepIndex - 1, steps);
  }, [stepIndex, steps, goToStep]);

  return {
    /** True only once the current step's anchor is confirmed present — gates rendering the
     *  spotlight so it never targets a not-yet-mounted node. */
    active: !!tourId && anchorReady,
    currentDef: anchorReady ? (steps[stepIndex] ?? null) : null,
    stepIndex,
    stepCount: steps.length,
    start,
    stop,
    next,
    prev,
  };
}
