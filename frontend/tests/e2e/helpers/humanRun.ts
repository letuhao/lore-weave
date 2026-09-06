/**
 * A recorded human-simulation run: one trace id per STEP, a snapshot per step, one manifest.
 *
 * WHAT THIS BUYS, AND WHY THE DEFAULTS WERE NOT ENOUGH
 * ────────────────────────────────────────────────────
 * Playwright's own capture is `screenshot: 'only-on-failure'` and `trace: 'retain-on-failure'`.
 * That is right for a suite whose job is red/green. It is the wrong shape for a human-simulation
 * run, whose output is a JUDGEMENT about quality — "did the assistant write five coherent
 * chapters" — where the interesting evidence is what the screen looked like when nothing failed.
 * A passing run under the default config leaves no artefact at all.
 *
 * The second half is correlation. `page.addInitScript` pins `window.__LW_TRACE_ID__` before the
 * step's first request, so every call that step makes carries the same `x-trace-id` and the log
 * collector can pull exactly those lines afterwards:
 *
 *     python scripts/e2e/collect_run_evidence.py --trace <the step's id> --out evidence/step-03
 *     python scripts/e2e/collect_run_evidence.py --label <runLabel>      --out evidence/all
 *
 * ⚠️ THE PIN IS SET ON THE NEXT NAVIGATION, NOT RETROACTIVELY. `addInitScript` runs at document
 * start, so an id pinned mid-page applies to requests made after it is set — which is what we
 * want per step — but a step that makes NO further requests will correlate to nothing, and the
 * collector will say so rather than reporting a clean scan. That is the honest failure.
 *
 * ⚠️ SNAPSHOTS ARE FULL-PAGE AND ARE NOT ASSERTIONS. Nothing here compares against a golden
 * image. A visual-regression baseline that nobody looks at goes stale and then fails for reasons
 * unrelated to the change; these exist to be READ by a person (or by the model writing the
 * report) and to be attached to a finding.
 */
import fs from 'node:fs';
import path from 'node:path';

import type { Page, TestInfo } from '@playwright/test';

export type StepRecord = {
  index: number;
  name: string;
  traceId: string;
  screenshot: string | null;
  startedAt: string;
  endedAt: string;
  ms: number;
  note?: string;
  error?: string;
};

/** Mirrors the server's `_TRACE_ID_RE`; an id outside it is replaced silently server-side. */
const TRACE_ID_RE = /^[A-Za-z0-9._-]{1,128}$/;

function slug(s: string): string {
  return s.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 48);
}

function randomHex(n: number): string {
  let out = '';
  for (let i = 0; i < n; i += 1) out += '0123456789abcdef'[Math.floor(Math.random() * 16)];
  return out;
}

export class HumanRun {
  readonly steps: StepRecord[] = [];
  readonly dir: string;

  constructor(
    private readonly page: Page,
    readonly runLabel: string,
    testInfo: TestInfo,
  ) {
    this.dir = path.join(testInfo.outputDir, `human-run-${slug(runLabel)}`);
    fs.mkdirSync(this.dir, { recursive: true });
  }

  /**
   * Run one step under its own trace id, snapshotting afterwards.
   *
   * The snapshot is taken even when the step THROWS, and the error is recorded on the step
   * rather than swallowed — a run that fails at step 4 of 9 should still leave the picture of
   * step 4, which is usually the one worth looking at. The throw is re-raised so the test still
   * fails; this records, it does not rescue.
   */
  async step<T>(name: string, fn: () => Promise<T>, note?: string): Promise<T> {
    const index = this.steps.length + 1;
    const traceId = `${slug(this.runLabel)}.${String(index).padStart(2, '0')}-${slug(name)}.${randomHex(8)}`;
    if (!TRACE_ID_RE.test(traceId)) {
      throw new Error(
        `humanRun: the generated trace id "${traceId}" is outside the server's accepted set, so ` +
        `the server would replace it and the log correlation would be lost without a word. ` +
        `Shorten the run label or the step name.`,
      );
    }
    const startedAt = new Date().toISOString();
    const t0 = Date.now();
    await this.page.addInitScript((id) => {
      (window as unknown as { __LW_TRACE_ID__?: string }).__LW_TRACE_ID__ = id;
    }, traceId);
    // Also set it on the CURRENT document: addInitScript only fires on the next navigation, and
    // a step that acts on the page already open would otherwise inherit the previous step's id.
    await this.page.evaluate((id) => {
      (window as unknown as { __LW_TRACE_ID__?: string }).__LW_TRACE_ID__ = id;
    }, traceId).catch(() => { /* no document yet — the init script covers the first navigation */ });

    let error: string | undefined;
    try {
      return await fn();
    } catch (e) {
      error = e instanceof Error ? `${e.name}: ${e.message}` : String(e);
      throw e;
    } finally {
      const file = path.join(this.dir, `${String(index).padStart(2, '0')}-${slug(name)}.png`);
      let screenshot: string | null = null;
      try {
        await this.page.screenshot({ path: file, fullPage: true });
        screenshot = file;
      } catch {
        // A closed page cannot be photographed. Recorded as null rather than failing the run
        // for a reason that is not the subject.
      }
      this.steps.push({
        index, name, traceId, screenshot,
        startedAt, endedAt: new Date().toISOString(), ms: Date.now() - t0,
        ...(note ? { note } : {}),
        ...(error ? { error } : {}),
      });
      this.flush();
    }
  }

  /** Write the manifest after every step, so a run killed mid-way still leaves its record. */
  private flush(): void {
    fs.writeFileSync(
      path.join(this.dir, 'run.json'),
      `${JSON.stringify({ runLabel: this.runLabel, steps: this.steps }, null, 2)}\n`,
      'utf8',
    );
  }
}

export function startHumanRun(page: Page, runLabel: string, testInfo: TestInfo): HumanRun {
  return new HumanRun(page, runLabel, testInfo);
}
