import { test, expect, type Page } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken,
  createBook,
  trashBook,
  listChatModels,
  createChatSession,
  deleteChatSession,
} from '../helpers/api';
import { StudioPage } from '../pages/StudioPage';

// Context Budget Law §11 — the Context Compiler · Trace Inspector, opened LIVE through
// its two real entry points (the studio Command Palette + the chat-header icon) against
// the real login/gateway/dockview stack. This is the committed live-gate the manual
// browser smoke automates (precedent: kg-panels.spec.ts / wiki-panels.spec.ts).
//
// The per-turn telemetry is MOCKED at `/context-trace` (the BE emit + endpoint are already
// covered by test_context_trace_contract.py / test_context_trace_router.py + the live
// scripts/context-inspector-trace-gate.py) so the render assertions are deterministic —
// this spec's job is the FE wiring no unit test can prove: the palette actually opens the
// dock panel, the chat icon deep-links with ?session, dockview mounts the shared view, and
// the real /context-trace shape drives the gauge/allocation/turn-list on screen.

function point(seq: number, statusFlags: string[], usedTokens: number, message: string) {
  return {
    sequence_num: seq,
    created_at: '2026-07-05T00:00:00Z',
    input_tokens: usedTokens,
    output_tokens: 40,
    user_message: message,
    frame: {
      used_tokens: usedTokens,
      context_length: 131072,
      effective_limit: 128000,
      pct: usedTokens / 128000,
      target: 32000,
      raw_tokens: usedTokens + 11400,
      reduction_pct: 0.48,
      status_flags: statusFlags,
      retrieval_mode: 'prepend',
      intent: 'status-op',
      entity_presence: { grounding_needed: false, matched: [], reason: 'no_entity' },
      until_compact_pct: 0.8,
      baseline_tokens: 1600,
      breakdown: {
        skills: 1500,
        history: 500,
        frontend_tool_schemas: 1000,
        memory_knowledge: { total: 500, sections: {} },
      },
      trace: [
        { phase: 'compiler', tier: 'T6', category: 'summary', action: 'C_persist: summarized 14 msgs', delta: -9800, is_error: false },
        { phase: 'compiler', tier: 'T0', category: 'results', action: 'wire hygiene: ensure_ascii=false', delta: -1600, is_error: false },
      ],
    },
  };
}

const TWO_TURNS = [
  point(1, ['gated', 'wire', 'compacted'], 12000, 'who is Lam Uyen'),
  point(2, ['included'], 40000, 'the over-target turn'),
];

/** Mock the Inspector's data feed so the render is deterministic. */
async function mockTrace(page: Page, items: unknown[]) {
  await page.route('**/context-trace**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items }) });
  });
}

test.describe('Context Compiler · Trace Inspector (live)', () => {
  let token: string;
  let bookId: string;
  let sessionId: string;
  let hasModel = false;

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    bookId = await createBook(request, token, `E2E Inspector ${Date.now()}`);
    const models = await listChatModels(request, token);
    hasModel = models.length > 0;
    if (hasModel) {
      const s = await createChatSession(request, token, models[0].user_model_id, `E2E Inspector ${Date.now()}`);
      sessionId = s.session_id;
    }
  });

  test.afterAll(async ({ request }) => {
    if (sessionId) await deleteChatSession(request, token, sessionId).catch(() => {});
    if (bookId) await trashBook(request, token, bookId).catch(() => {});
  });

  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  test('chat-header icon deep-links to the inspector focused on THIS session + renders real trace', async ({ page }) => {
    test.skip(!hasModel, 'needs a chat model to create a session');
    await mockTrace(page, TWO_TURNS);
    // Deep-link straight to the session by URL. This also regression-guards
    // D-CHAT-URL-SESSION-ACTIVATION: a fresh 0-message session sorts to the bottom
    // by last-activity, so it is NOT in the first page of the loaded list — the
    // provider now fetches it individually so the session activates instead of
    // silently showing an empty chat.
    await page.goto(`/chat/${sessionId}`);

    // the header inspector affordance is present once the session activates
    const btn = page.getByTestId('chat-context-inspector-button');
    await expect(btn).toBeVisible({ timeout: 15_000 });
    await btn.click();

    // deep-linked to the standalone inspector scoped to THIS exact session
    await expect(page).toHaveURL(new RegExp(`/context-inspector\\?session=${sessionId}`));
    await expect(page.getByTestId('context-inspector')).toBeVisible();

    // the real /context-trace shape drives the hero gauge + allocation map + turn list
    await expect(page.getByTestId('inspector-gauge')).toBeVisible();
    await expect(page.getByTestId('inspector-gauge').locator('svg')).toHaveAttribute('data-gauge-state', /under|over-target|over-ceiling/);
    await expect(page.getByTestId('inspector-allocation').locator('[data-alloc-seg]').first()).toBeVisible();
    await expect(page.getByTestId('inspector-turn-list').locator('[data-turn-seq]')).toHaveCount(2);
  });

  test('status filter narrows the turn list live (verify-by-effect through the real DOM)', async ({ page }) => {
    test.skip(!hasModel, 'needs a chat model to create a session');
    await mockTrace(page, TWO_TURNS);
    await page.goto(`/context-inspector?session=${sessionId}`);

    const list = page.getByTestId('inspector-turn-list');
    await expect(list.locator('[data-turn-seq]')).toHaveCount(2);
    // clicking "gated" keeps only turn 1 (turn 2 is 'included', not gated)
    await list.locator('[data-status-filter="gated"]').click();
    await expect(list.locator('[data-turn-seq]')).toHaveCount(1);
    await expect(list.locator('[data-turn-seq="1"]')).toBeVisible();
  });

  test('opens as a dock panel via the studio Command Palette', async ({ page }) => {
    // list-sessions is mocked so the self-contained picker deterministically lands on our turn set
    await page.route(/\/v1\/chat\/sessions(\?|$)/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [{ session_id: 'e2e-mock-session', title: 'E2E Inspector Session' }] }),
      });
    });
    await mockTrace(page, TWO_TURNS);

    const studio = new StudioPage(page);
    await studio.goto(bookId);
    await studio.openPanel('context-inspector', 'Context Inspector');

    await expect(page.getByTestId('studio-context-inspector-panel')).toBeVisible();
    await expect(page.getByTestId('context-inspector')).toBeVisible();
    await expect(page.getByTestId('inspector-gauge')).toBeVisible();
  });

  test('a session with no measured turns shows the honest empty state', async ({ page }) => {
    test.skip(!hasModel, 'needs a chat model to create a session');
    await mockTrace(page, []);
    await page.goto(`/context-inspector?session=${sessionId}`);
    await expect(page.getByText(/no measured turns in this session yet/i)).toBeVisible();
  });
});
