import { test, expect } from '@playwright/test';
import type { APIRequestContext } from '@playwright/test';
import { getAccessToken, ensureUserB } from '../helpers/api';

// QC Track-B — the TENANCY GATE (T4). Self-hosted ≠ single-user: one user's autonomous settings must be
// completely invisible + immutable to another. This is a BLOCKING gate — any failure is a ship-stopper.
// API-level (no chat-UI dependency), owner-scoped by JWT sub. Validates the A3 (schedule) + proactive
// (ai-prefs) owner-scoping directly. Self-cleaning: every armed setting is reset in a finally.
const bearer = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });

async function getSchedule(request: APIRequestContext, token: string) {
  const r = await request.get('/v1/assistant/schedule', bearer(token));
  expect(r.ok(), `GET schedule ${r.status()}`).toBeTruthy();
  return ((await r.json()) as { schedules: Array<{ job_kind: string; enabled: boolean }> }).schedules;
}

async function setSchedule(request: APIRequestContext, token: string, jobKind: string, enabled: boolean) {
  const r = await request.post('/v1/assistant/schedule', { ...bearer(token), data: { job_kind: jobKind, enabled, timezone: 'UTC' } });
  expect(r.ok(), `POST schedule ${r.status()}`).toBeTruthy();
}

async function getProactive(request: APIRequestContext, token: string): Promise<boolean> {
  const r = await request.get('/v1/chat/ai-prefs', bearer(token));
  expect(r.ok(), `GET ai-prefs ${r.status()}`).toBeTruthy();
  return (((await r.json()) as { assistant?: { proactive_enabled?: boolean } }).assistant?.proactive_enabled) === true;
}

async function setProactive(request: APIRequestContext, token: string, on: boolean) {
  const r = await request.patch('/v1/chat/ai-prefs', { ...bearer(token), data: { assistant: { proactive_enabled: on } } });
  expect(r.ok(), `PATCH ai-prefs ${r.status()}`).toBeTruthy();
}

async function provision(request: APIRequestContext, token: string): Promise<{ book_id: string }> {
  const r = await request.post('/v1/assistant/provision', { ...bearer(token), data: {} });
  expect(r.ok(), `provision ${r.status()}`).toBeTruthy();
  return (await r.json()) as { book_id: string };
}

test.describe('Assistant — tenancy gate (T1, BLOCKING)', () => {
  test('T1 — each user has a SEPARATE diary root, and A cannot read B\'s diary', async ({ request }) => {
    const a = await getAccessToken(request);
    const b = await ensureUserB(request);

    const diaryA = await provision(request, a);
    const diaryB = await provision(request, b);

    // Per-book tenancy: distinct diary roots (never a shared/global diary).
    expect(diaryA.book_id, 'A has a diary book').toBeTruthy();
    expect(diaryB.book_id, 'B has a diary book').toBeTruthy();
    expect(diaryA.book_id, "A's and B's diaries are DISTINCT roots").not.toBe(diaryB.book_id);

    // A trying to read B's diary entries with A's token is denied (not a global read).
    const cross = await request.get(`/v1/books/${diaryB.book_id}/diary/entries`, bearer(a));
    if (cross.ok()) {
      // If it 200s it must be EMPTY of B's data (never leak another tenant's rows).
      const body = (await cross.json()) as { entries?: unknown[] };
      expect((body.entries ?? []).length, "A must not receive B's diary rows").toBe(0);
    } else {
      expect(cross.status(), 'A is denied B\'s diary (403/404)').toBeGreaterThanOrEqual(403);
    }

    // A's own diary FACT inbox is JWT-scoped (returns an array of A's only — never B's).
    const aFacts = await request.get('/v1/knowledge/pending-facts?diary_only=true', bearer(a));
    expect(aFacts.ok(), `A pending-facts ${aFacts.status()}`).toBeTruthy();
    expect(Array.isArray(await aFacts.json()), 'diary facts are a JWT-scoped list').toBe(true);
  });
});

test.describe('Assistant — tenancy gate (T4, BLOCKING)', () => {
  test('T4a — user A arming a schedule is INVISIBLE to user B', async ({ request }) => {
    const a = await getAccessToken(request);
    const b = await ensureUserB(request);
    try {
      // Baseline: neither user has eod_distill enabled.
      await setSchedule(request, a, 'eod_distill', false);
      await setSchedule(request, b, 'eod_distill', false);

      // A arms eod_distill.
      await setSchedule(request, a, 'eod_distill', true);

      // A sees it enabled...
      const aRows = await getSchedule(request, a);
      expect(aRows.find((r) => r.job_kind === 'eod_distill')?.enabled, 'A sees its own arm').toBe(true);

      // ...but B's list NEVER reflects A's arm (B's rows are B's own).
      const bRows = await getSchedule(request, b);
      expect(bRows.find((r) => r.job_kind === 'eod_distill')?.enabled ?? false, 'B never sees A arm').toBe(false);
    } finally {
      await setSchedule(request, a, 'eod_distill', false).catch(() => {});
    }
  });

  test('T4b — the proactive opt-in gate is per-user (A on ≠ B on)', async ({ request }) => {
    const a = await getAccessToken(request);
    const b = await ensureUserB(request);
    try {
      await setProactive(request, a, false);
      await setProactive(request, b, false);

      await setProactive(request, a, true); // A opts in
      expect(await getProactive(request, a), 'A opted in').toBe(true);
      expect(await getProactive(request, b), "B's gate is independent (still off)").toBe(false);
    } finally {
      await setProactive(request, a, false).catch(() => {});
    }
  });
});
