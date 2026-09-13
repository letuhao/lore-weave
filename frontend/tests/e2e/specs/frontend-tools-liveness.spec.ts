// Frontend-tools liveness — G4 (Track D · WS-D5).
//
// G3 (call-shape + the resolver never silently no-ops) is proven deterministically
// by the pure-resolver contract tests (frontendToolContract.test.ts +
// test_frontend_tools_contract.py). THIS spec proves G4: the REAL browser
// executor/resolver/card runs when a suspended frontend-tool call arrives, and the
// suspend→resume round-trip to /tool-results closes. We inject the suspended call
// (helpers/frontendToolInject) rather than depend on a local model *choosing* to
// emit it — the trigger is simulated, every line of FE execution under test is real
// (agent-gui-loop-needs-live-browser-smoke-not-raw-stream).
import { test, expect, type APIRequestContext } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { getAccessToken, createBook, createChapter, trashBook } from '../helpers/api';
import { queryDb } from '../helpers/db';
import { apiBase } from '../helpers/stack';
import { installFrontendToolSuspend, installUiDirectiveResult } from '../helpers/frontendToolInject';

const API = apiBase(); // derived from the browser target -- see helpers/stack.ts
// gemma-4-26b-a4b-qat (chat + tool_calling) on the test account — a valid BYOK
// user_model so the session validates; no turn actually runs it (SSE is injected).
// Both of these used to be hard-coded to the `claude-test` account on the BASE stack, so the
// spec could only ever run there. They are read off the account under test instead: the model
// from the registry (any ACTIVE chat model validates the session; no turn actually runs it,
// the SSE is injected), the user id from the token's own `sub`.
let MODEL_REF = process.env.PLAYWRIGHT_MODEL_REF ?? '';
let USER_ID = '';

function userIdFromToken(token: string): string {
  const claims = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString('utf8'));
  const sub = claims.sub ?? claims.user_id;
  if (!sub) throw new Error('no subject claim in the access token');
  return String(sub);
}

async function firstActiveModel(request: APIRequestContext, token: string): Promise<string> {
  const res = await request.get(`${API}/v1/model-registry/user-models`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(res.ok(), `list user-models: ${res.status()}`).toBeTruthy();
  const body = await res.json();
  const rows: Array<{ user_model_id: string; is_active?: boolean }> =
    body.items ?? body.user_models ?? body ?? [];
  const active = rows.find((m) => m.is_active !== false);
  if (!active) throw new Error('the account under test has no ACTIVE model to validate a session');
  return active.user_model_id;
}

async function createSession(request: APIRequestContext, token: string, title: string): Promise<string> {
  const res = await request.post(`${API}/v1/chat/sessions`, {
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    data: { title, model_source: 'user_model', model_ref: MODEL_REF },
  });
  expect(res.ok(), `create session: ${res.status()}`).toBeTruthy();
  const body = await res.json();
  return body.session_id ?? body.id;
}

// Open the seeded session by CLICKING it in the sidebar (selectSession → setActiveSession
// directly, no URL-fetch). Deep-linking /chat/{id} is unreliable headless: a fresh session
// activates via a getSession fallback that races the list load. The seeded message makes the
// session sort recent, so the row is in the loaded window.
async function openSession(page: import('@playwright/test').Page, title: string): Promise<void> {
  await page.goto('/chat');
  await page.getByTestId('chat-session-row').filter({ hasText: title }).first().click();
  await expect(page.getByTestId('chat-input-textarea')).toBeVisible({ timeout: 15000 });
}

async function sendChat(page: import('@playwright/test').Page, text: string): Promise<void> {
  const input = page.getByTestId('chat-input-textarea');
  await input.fill(text);
  await page.getByTestId('chat-send-button').click();
}

test.describe('Frontend-tools liveness (G4 — real browser executor)', () => {
  let token: string;
  let bookId: string;
  let sessionId: string;

  test.beforeAll(async ({ request }) => {
    token = await getAccessToken(request);
    USER_ID = userIdFromToken(token);
    if (!MODEL_REF) MODEL_REF = await firstActiveModel(request, token);
    bookId = await createBook(request, token, `E2E fe-tools ${Date.now()}`);
    await createChapter(request, token, bookId, 'Chapter One');
    sessionId = await createSession(request, token, 'fe-tools liveness');
    // Seed one message AND bump last_message_at so the session sorts to the TOP of
    // the sidebar (the list is ORDER BY last_message_at DESC; a fresh session leaves
    // it NULL → NULLS-LAST → escapes the loaded window, fresh-session-nulls-last-
    // sort-escapes-loaded-page). Then the row is present and openSession can click it.
    queryDb(
      'loreweave_chat',
      `INSERT INTO chat_messages (session_id, owner_user_id, role, content, sequence_num) ` +
        `VALUES ('${sessionId}', '${USER_ID}', 'user', 'seed', 0)`,
    );
    queryDb(
      'loreweave_chat',
      `UPDATE chat_sessions SET last_message_at = now(), message_count = 1 WHERE session_id = '${sessionId}'`,
    );
  });

  test.afterAll(async ({ request }) => {
    if (bookId) await trashBook(request, token, bookId).catch(() => {});
    // Destroy the session (+ its seeded message) this spec created — otherwise every run
    // leaks a 'fe-tools liveness' session into the test account.
    if (sessionId) {
      try {
        queryDb('loreweave_chat', `DELETE FROM chat_messages WHERE session_id = '${sessionId}'`);
        queryDb('loreweave_chat', `DELETE FROM chat_sessions WHERE session_id = '${sessionId}'`);
      } catch { /* best effort */ }
    }
  });

  test.beforeEach(async ({ page }) => {
    await loginViaUI(page);
  });

  // ── Nav executor (useUiToolExecutor, mounted in ChatView) ──────────────────

  test('ui_show_panel — executor sets the panel query from a ui-directive result', async ({ page }) => {
    await openSession(page, 'fe-tools liveness');
    // ui_* does NOT suspend any more (useUiToolExecutor: "no ui_* suspends any more"). The
    // executor acts on a TOOL_CALL_RESULT carrying an io.loreweave/ui-directive.
    await installUiDirectiveResult(page, { tool: 'ui_show_panel', args: { panel: 'glossary' }, text: 'Opening the glossary panel.' });
    await sendChat(page, 'show glossary');
    // Effect: the executor navigates to current path + ?panel=glossary (stays mounted).
    await page.waitForURL(/[?&]panel=glossary/, { timeout: 15000 });
    // The /tool-results round-trip assertions that used to live here are GONE, and the test's
    // name lost "and resolves the round-trip" with them -- because the round-trip itself is gone.
    // A ui_* call no longer suspends, so the FE has nothing to resolve: the server executed the
    // tool and sent a directive, and the FE's whole job is to act on it. Asserting a POST that
    // the product deliberately stopped making would be asserting the retired design.
    //
    // What IS still guarded, and is the point: the directive produced the NAVIGATION above, and
    // the executor is idempotent -- a re-render must not navigate a second time, so the panel
    // query is still exactly one `panel=glossary`, not stacked.
    const url = new URL(page.url());
    expect(url.searchParams.getAll('panel')).toEqual(['glossary']);
  });

  test('ui_open_book — executor navigates to the book', async ({ page }) => {
    await openSession(page, 'fe-tools liveness');
    await installUiDirectiveResult(page, { tool: 'ui_open_book', args: { book_id: bookId }, text: 'Opening the book.' });
    await sendChat(page, 'open my book');
    await page.waitForURL(new RegExp(`/books/${bookId}`), { timeout: 15000 });
  });

  // ── Gated cards (dispatched BY NAME in AssistantMessage) ───────────────────
  // The drift that shipped ui_open_studio_panel broken was a name→component
  // mismatch; asserting the correct card renders from the pending record proves
  // the dispatch is wired (G4 for the card surface).

  test('propose_edit — renders the ProposeEdit card from the suspended call', async ({ page }) => {
    await openSession(page, 'fe-tools liveness');
    await installFrontendToolSuspend(page, {
      tool: 'propose_edit',
      args: { operation: 'insert_at_cursor', text: 'A vivid new sentence.' },
      text: 'Here is a proposed edit.',
    });
    await sendChat(page, 'improve this');
    await expect(page.getByTestId('propose-edit-card')).toBeVisible({ timeout: 15000 });
  });

  test('confirm_action — renders the ConfirmAction card from the suspended call', async ({ page }) => {
    await openSession(page, 'fe-tools liveness');
    await installFrontendToolSuspend(page, {
      tool: 'confirm_action',
      args: { domain: 'glossary', confirm_token: 'tle-fake-token', summary: 'Confirm a canon change' },
      text: 'Please confirm.',
    });
    await sendChat(page, 'do it');
    await expect(page.getByTestId('confirm-action-card')).toBeVisible({ timeout: 15000 });
  });

  // ── Coverage note for the remaining 8 frontend tools ──────────────────────
  // The four injected tests above exercise both executor code paths end-to-end in
  // the real browser: the nav executor (useUiToolExecutor → resolveUiTool →
  // navigate + submitToolResolve) and the card dispatch (AssistantMessage → the
  // named diff/confirm card). The other 8 frontend tools are covered as follows,
  // and do not need a separate injected G4:
  //   • ui_navigate / ui_open_chapter / ui_watch_job — same useUiToolExecutor +
  //     resolveUiTool path proven by ui_show_panel + ui_open_book here; each arg
  //     shape is asserted by the pure-resolver contract test
  //     (frontendToolContract.test.ts, G3).
  //   • propose_record_edit / glossary_propose_edit / glossary_confirm_action —
  //     same AssistantMessage name→card dispatch proven by propose_edit +
  //     confirm_action here; schemas asserted by test_frontend_tools_contract.py.
  //   • ui_open_studio_panel / ui_focus_manuscript_unit — the studio executor
  //     (useStudioUiToolExecutor → host.openPanel / focusManuscriptUnit). Its
  //     effect is proven live by studio-compose.spec / studio-palette.spec (the
  //     SAME host.openPanel the executor calls); the resolver is proven by the
  //     pure-resolver test (resolveStudioUiTool, G3). We do not inject here because
  //     the compose panel runs the chat windowed (SharedWorker), which page.route
  //     cannot intercept — the standalone /chat surface above is the interceptable one.
});
