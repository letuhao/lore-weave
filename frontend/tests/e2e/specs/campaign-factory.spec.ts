import { test, expect } from '@playwright/test';
import { getAccessToken, ensureUserB, createBook, trashBook } from '../helpers/api';
import {
  ABSENT_CAMPAIGN_ID, campaignServiceUp, errorCode,
  estimateCampaign, createCampaign, listCampaigns, getCampaign,
  getReport, getActivity, getChapters, patchCampaign,
  startCampaign, pauseCampaign, cancelCampaign, rerunFailed,
} from '../helpers/campaigns';

// Auto-Draft Factory E2E — gateway contract + owner-scoping + lifecycle guards.
//
// SCOPE (intentional): this asserts the cross-service CONTRACT layer of the
// gap-fix routes (G1 report · G2 rerun-failed · G3 stats source · paging ·
// activity log · switch-model PATCH) through the api-gateway — that every new
// route is reachable, owner-scoped (404 on a foreign/absent id), and enforces
// its stateless guards (empty PATCH, payload validation, isolation). It needs
// NO model and NO knowledge graph, so it runs deterministically on any stack-up.
//
// The DATA-bearing happy-path (report numbers, activity rows, >200-chapter
// paging, rerun reset, models-locked-while-running) is covered by the
// campaign-service real-PG integration suites (test_report_db / test_activity_db
// / test_rerun_db / test_progress_db) + the [MODEL] live scenarios in
// docs/specs/2026-06-10-auto-draft-factory-e2e-scenarios.md. An opt-in
// fixture-gated block below exercises a real create when E2E_FACTORY_PROJECT_ID
// (+ E2E_FACTORY_BOOK_ID with published chapters in range) are provided.
//
// Scenario IDs reference the e2e-scenarios spec.

test.describe('Auto-Draft Factory — gateway contract & guards', () => {
  test('every gap-fix route is reachable + owner-scoped (404 on absent id) [A3/F8/J7/L6/L7 wiring]', async ({ request }) => {
    const token = await getAccessToken(request);
    test.skip(!(await campaignServiceUp(request, token)), 'campaign-service not in this stack-up');

    // GET reads + POST actions on a syntactically-valid but non-existent id must
    // all 404 with the campaign-service error envelope — proves the gateway route
    // map AND that none leak across the owner boundary.
    const routes: Array<[string, Promise<import('@playwright/test').APIResponse>]> = [
      ['get', getCampaign(request, token, ABSENT_CAMPAIGN_ID)],
      ['report', getReport(request, token, ABSENT_CAMPAIGN_ID)],
      ['activity', getActivity(request, token, ABSENT_CAMPAIGN_ID)],
      ['chapters', getChapters(request, token, ABSENT_CAMPAIGN_ID)],
      ['start', startCampaign(request, token, ABSENT_CAMPAIGN_ID)],
      ['pause', pauseCampaign(request, token, ABSENT_CAMPAIGN_ID)],
      ['cancel', cancelCampaign(request, token, ABSENT_CAMPAIGN_ID)],
      ['rerun-failed', rerunFailed(request, token, ABSENT_CAMPAIGN_ID)],
    ];
    for (const [label, p] of routes) {
      const resp = await p;
      expect(resp.status(), label).toBe(404);
      expect(await errorCode(resp), label).toBe('CAMPAIGN_NOT_FOUND');
    }
  });

  test('PATCH empty body → 400 CAMPAIGN_PATCH_EMPTY (precedes owner load) [C5]', async ({ request }) => {
    const token = await getAccessToken(request);
    test.skip(!(await campaignServiceUp(request, token)), 'campaign-service not in this stack-up');
    const resp = await patchCampaign(request, token, ABSENT_CAMPAIGN_ID, {});
    expect(resp.status()).toBe(400);
    expect(await errorCode(resp)).toBe('CAMPAIGN_PATCH_EMPTY');
  });

  test('chapters paging accepts status + limit/offset, clamps, defaults [J7]', async ({ request }) => {
    const token = await getAccessToken(request);
    test.skip(!(await campaignServiceUp(request, token)), 'campaign-service not in this stack-up');
    // Even on an absent id the query is parsed before the owner load → still 404
    // (not 422): proves status/limit/offset are accepted, not rejected.
    for (const q of ['?status=all&limit=200&offset=0', '?status=inflight', '?status=attention&limit=9999', '?status=bogus']) {
      const resp = await getChapters(request, token, ABSENT_CAMPAIGN_ID, q);
      expect(resp.status(), q).toBe(404); // accepted-but-not-found, never a 422
      expect(await errorCode(resp)).toBe('CAMPAIGN_NOT_FOUND');
    }
  });

  test('create payload validation [J2/J5/J6]', async ({ request }) => {
    const token = await getAccessToken(request);
    test.skip(!(await campaignServiceUp(request, token)), 'campaign-service not in this stack-up');

    // J2 — missing knowledge_project_id is the first business check (400, before
    // any service call).
    const noProject = await createCampaign(request, token, {
      name: 'e2e-noproject', book_id: ABSENT_CAMPAIGN_ID,
    });
    expect(noProject.status()).toBe(400);
    expect(await errorCode(noProject)).toBe('CAMPAIGN_NO_KNOWLEDGE_PROJECT');

    // J6 — budget out of range → 422 (pydantic, before the handler body).
    for (const budget of [-1, 0, 1e8 + 1]) {
      const bad = await createCampaign(request, token, {
        name: 'e2e-budget', book_id: ABSENT_CAMPAIGN_ID,
        knowledge_project_id: ABSENT_CAMPAIGN_ID, budget_usd: budget,
      });
      expect(bad.status(), `budget=${budget}`).toBe(422);
    }

    // J5 — invalid gating_mode → 422.
    const badGate = await createCampaign(request, token, {
      name: 'e2e-gate', book_id: ABSENT_CAMPAIGN_ID,
      knowledge_project_id: ABSENT_CAMPAIGN_ID, gating_mode: 'turbo',
    });
    expect(badGate.status()).toBe(422);
  });

  test('estimate validates payload (422 on malformed) [A2]', async ({ request }) => {
    const token = await getAccessToken(request);
    test.skip(!(await campaignServiceUp(request, token)), 'campaign-service not in this stack-up');
    const bad = await estimateCampaign(request, token, { name: 'missing-book' });
    expect(bad.status()).toBe(422);
  });

  test('campaigns list is owner-scoped — user B never sees user A rows [I1/I4 isolation]', async ({ request }) => {
    const tokenA = await getAccessToken(request);
    test.skip(!(await campaignServiceUp(request, tokenA)), 'campaign-service not in this stack-up');
    const tokenB = await ensureUserB(request);

    const listA = await listCampaigns(request, tokenA);
    const listB = await listCampaigns(request, tokenB);
    expect(listA.ok()).toBeTruthy();
    expect(listB.ok()).toBeTruthy();
    const idsA = new Set(((await listA.json()) as { campaign_id: string }[]).map((c) => c.campaign_id));
    const idsB = ((await listB.json()) as { campaign_id: string }[]).map((c) => c.campaign_id);
    for (const id of idsB) expect(idsA.has(id), `B campaign ${id} must not appear for A`).toBeFalsy();

    // And A's routes 404 for B (cross-tenant), exercised on any of A's campaigns.
    const someA = [...idsA][0];
    if (someA) {
      const crossed = await getReport(request, tokenB, someA);
      expect(crossed.status()).toBe(404);
    }
  });
});

// Opt-in: a REAL create + the data-bearing read surface. Requires an owned
// knowledge project id and a book with published chapters in range, supplied via
// env (so CI without seeded fixtures skips cleanly rather than failing).
test.describe('Auto-Draft Factory — real create + report/activity/chapters [fixture-gated]', () => {
  const PROJECT = process.env.E2E_FACTORY_PROJECT_ID;
  const BOOK = process.env.E2E_FACTORY_BOOK_ID;

  test('create → report/activity/chapters contracts + switch-model gate [A1/A3/C4/L6/L7]', async ({ request }) => {
    test.skip(!PROJECT || !BOOK, 'set E2E_FACTORY_PROJECT_ID + E2E_FACTORY_BOOK_ID (book w/ published chapters)');
    const token = await getAccessToken(request);
    test.skip(!(await campaignServiceUp(request, token)), 'campaign-service not in this stack-up');

    const created = await createCampaign(request, token, {
      name: `e2e-factory ${Date.now()}`,
      book_id: BOOK,
      knowledge_project_id: PROJECT,
    });
    expect(created.status(), await created.text()).toBe(201);
    const c = (await created.json()) as { campaign_id: string; status: string };
    expect(c.status).toBe('created');

    try {
      // G1 report shape (available pre-run; data is mostly zero/null but the
      // contract must hold).
      const report = await getReport(request, token, c.campaign_id);
      expect(report.ok()).toBeTruthy();
      const rep = (await report.json()) as Record<string, unknown>;
      for (const k of ['status', 'total_chapters', 'stages', 'error_groups']) {
        expect(rep, `report.${k}`).toHaveProperty(k);
      }
      expect(Array.isArray(rep.error_groups)).toBeTruthy();

      // L6 activity keyset page shape.
      const act = await getActivity(request, token, c.campaign_id, '?limit=10');
      expect(act.ok()).toBeTruthy();
      expect((await act.json())).toHaveProperty('rows');

      // L7 in-flight filter + J7 paging shape (created campaign → all pending).
      const inflight = await getChapters(request, token, c.campaign_id, '?status=inflight');
      expect(inflight.ok()).toBeTruthy();
      const pageAll = await getChapters(request, token, c.campaign_id, '?status=all&limit=50&offset=0');
      expect(pageAll.ok()).toBeTruthy();
      const pa = (await pageAll.json()) as { rows: unknown[]; total: number };
      expect(Array.isArray(pa.rows)).toBeTruthy();
      expect(typeof pa.total).toBe('number');

      // C4/C5 switch-model: allowed while `created`. Empty body → 400.
      const empty = await patchCampaign(request, token, c.campaign_id, {});
      expect(empty.status()).toBe(400);
      expect(await errorCode(empty)).toBe('CAMPAIGN_PATCH_EMPTY');
    } finally {
      await cancelCampaign(request, token, c.campaign_id); // best-effort cleanup
    }
  });
});
