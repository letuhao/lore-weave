import { test, expect } from '@playwright/test';
import type { APIRequestContext } from '@playwright/test';
import { AssistantPage } from '../pages/AssistantPage';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken } from '../helpers/api';

// QC Track-B — S10b: arming an autonomous job through the UI actually persists an ARMED schedule row
// server-side (the fail-closed opt-in becomes a real trigger). The scheduler's tick then firing that row is
// proven by the A3 live-smoke (ca372d6eb) — a 60s+ scheduler-tick wait is unsuitable for a fast spec, so
// this asserts the arming half by EFFECT (UI toggle → server row enabled + next_fire_at set → toggle OFF
// disarms). Self-cleaning (always leaves eod_distill OFF).
const bearer = (t: string) => ({ headers: { Authorization: `Bearer ${t}` } });

async function scheduleRow(request: APIRequestContext, token: string, kind: string) {
  const r = await request.get('/v1/assistant/schedule', bearer(token));
  expect(r.ok(), `GET schedule ${r.status()}`).toBeTruthy();
  const rows = ((await r.json()) as { schedules: Array<{ job_kind: string; enabled: boolean; next_fire_at?: string | null }> }).schedules;
  return rows.find((s) => s.job_kind === kind);
}

test.describe('Assistant — autonomous arming persists a real schedule (S10b)', () => {
  test('toggling eod_distill ON arms a server row (enabled + next_fire_at); OFF disarms', async ({ page, request }) => {
    const token = await getAccessToken(request);
    await loginViaUI(page);
    const a = new AssistantPage(page);
    await a.goto();
    const toggle = a.autonomousToggle('eod_distill');

    try {
      // Precondition: OFF (fail-closed). If a prior run left it on, this test's own toggle sequence resets it.
      await expect(toggle).toBeVisible();

      // ARM through the UI — the toggle writes server-side then re-reads; aria-checked flips to true.
      if (!(await AssistantPage.isOn(toggle))) await a.clickAutonomousToggle('eod_distill');
      await expect(toggle).toHaveAttribute('aria-checked', 'true');

      // Verify BY EFFECT on the server: the row is enabled AND armed to a concrete next fire instant.
      const armed = await scheduleRow(request, token, 'eod_distill');
      expect(armed?.enabled, 'server row enabled').toBe(true);
      expect(armed?.next_fire_at, 'server row armed to a next fire instant').toBeTruthy();

      // DISARM — the toggle flips back and the server row goes disabled.
      await a.clickAutonomousToggle('eod_distill');
      await expect(toggle).toHaveAttribute('aria-checked', 'false');
      const off = await scheduleRow(request, token, 'eod_distill');
      expect(off?.enabled ?? false, 'server row disabled after OFF').toBe(false);
    } finally {
      // Belt-and-braces cleanup: ensure eod_distill is OFF regardless of where the test failed.
      await request.post('/v1/assistant/schedule', { ...bearer(token), data: { job_kind: 'eod_distill', enabled: false, timezone: 'UTC' } }).catch(() => {});
    }
  });
});
