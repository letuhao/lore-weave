import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import {
  getAccessToken,
  listChatModels,
  createChatSession,
  deleteChatSession,
  patchChatSession,
  getChatSession,
  getToolsCatalog,
  getSkillsCatalog,
} from '../helpers/api';

function sseBody(lines: string[]): string {
  return lines.map((line) => `data: ${line}\n\n`).join('');
}

test.describe('Agent context rack (story 04)', () => {
  test('API smoke — catalogs + PATCH enabled_tools round-trip', async ({ request }) => {
    const token = await getAccessToken(request);
    const models = await listChatModels(request, token);
    test.skip(models.length < 1, 'needs a chat model');
    const session = await createChatSession(request, token, models[0].user_model_id, `E2E rack API ${Date.now()}`);
    try {
      const tools = await getToolsCatalog(request, token);
      const skills = await getSkillsCatalog(request, token);
      expect(tools.items.length).toBeGreaterThan(0);
      expect(skills.items.length).toBeGreaterThan(0);

      await patchChatSession(request, token, session.session_id, { enabled_tools: ['find_tools'] });
      const got = await getChatSession(request, token, session.session_id);
      expect(got.enabled_tools).toEqual(['find_tools']);
    } finally {
      await deleteChatSession(request, token, session.session_id).catch(() => {});
    }
  });

  test('rack UI — pin tool triggers PATCH', async ({ page, request }) => {
    test.setTimeout(60_000);
    const token = await getAccessToken(request);
    const models = await listChatModels(request, token);
    test.skip(models.length < 1, 'needs a chat model');
    const session = await createChatSession(request, token, models[0].user_model_id, `E2E rack UI ${Date.now()}`);

    await page.route('**/v1/chat/tools/catalog', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [{ name: 'mock_find_tool', description: 'Mock tool', domain: 'test', tier: 'R' }],
        }),
      });
    });
    await page.route('**/v1/chat/skills/catalog', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [{ id: 'universal', label: 'Universal', surfaces: ['chat'] }],
        }),
      });
    });

    try {
      await loginViaUI(page);
      await page.goto(`/chat/${session.session_id}`);

      const rack = page.getByTestId('agent-context-rack');
      await expect(rack).toBeVisible({ timeout: 15_000 });

      const patchPromise = page.waitForRequest((req) =>
        req.method() === 'PATCH'
        && req.url().includes(`/v1/chat/sessions/${session.session_id}`)
        && (req.postDataJSON()?.enabled_tools ?? []).includes('mock_find_tool'),
      );

      await page.getByTestId('agent-rack-add').click();
      await page.getByRole('button', { name: 'mock_find_tool' }).click();

      await patchPromise;
      await expect(page.getByTestId('agent-rack-chip-tool-mock_find_tool')).toBeVisible();
    } finally {
      await deleteChatSession(request, token, session.session_id).catch(() => {});
    }
  });

  test('mock SSE — agentSurface phases update inspector', async ({ page, request }) => {
    test.setTimeout(60_000);
    const token = await getAccessToken(request);
    const models = await listChatModels(request, token);
    test.skip(models.length < 1, 'needs a chat model');
    const session = await createChatSession(request, token, models[0].user_model_id, `E2E inspector ${Date.now()}`);

    const agentCurated = JSON.stringify({
      type: 'CUSTOM',
      name: 'agentSurface',
      value: {
        phase: 'Curated',
        pinned_count: 0,
        hot_seed_count: 3,
        activated_count: 0,
        injected_skills: ['universal'],
        running_tool: null,
        last_find_tools_query: null,
        find_tools_call_count: 0,
      },
    });
    const agentIdle = JSON.stringify({
      type: 'CUSTOM',
      name: 'agentSurface',
      value: {
        phase: 'Idle',
        pinned_count: 0,
        hot_seed_count: 3,
        activated_count: 0,
        injected_skills: ['universal'],
        running_tool: null,
        last_find_tools_query: null,
        find_tools_call_count: 0,
      },
    });

    await page.route(`**/v1/chat/sessions/${session.session_id}/messages`, async (route) => {
      if (route.request().method() !== 'POST') {
        await route.continue();
        return;
      }
      const body = route.request().postDataJSON() as { content?: string };
      expect(body.content).toBeTruthy();
      await route.fulfill({
        status: 200,
        headers: {
          'Content-Type': 'text/event-stream',
          'x-loreweave-stream-format': 'agui',
        },
        body: sseBody([
          JSON.stringify({ type: 'RUN_STARTED', threadId: session.session_id, runId: 'r1' }),
          agentCurated,
          JSON.stringify({ type: 'TEXT_MESSAGE_START', messageId: 'm1', role: 'assistant' }),
          JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: 'Hello.' }),
          JSON.stringify({ type: 'TEXT_MESSAGE_END', messageId: 'm1' }),
          agentIdle,
          JSON.stringify({ type: 'RUN_FINISHED', result: {} }),
        ]),
      });
    });

    try {
      await loginViaUI(page);
      await page.goto(`/chat/${session.session_id}`);

      await expect(page.getByTestId('agent-runtime-inspector')).toBeVisible({ timeout: 15_000 });
      const phase = page.getByTestId('agent-inspector-phase');
      await expect(phase).toHaveText('Idle', { timeout: 15_000 });

      const textarea = page.getByRole('textbox').first();
      await textarea.fill('ping');
      await page.getByTitle('Send').click();

      await expect(phase).toHaveText('Curated', { timeout: 10_000 });
      await expect(phase).toHaveText('Idle', { timeout: 10_000 });
    } finally {
      await deleteChatSession(request, token, session.session_id).catch(() => {});
    }
  });
});

test.describe('Agent context rack live [model-gated]', () => {
  test('pin + send — inspector leaves Idle', async ({ page, request }) => {
    test.setTimeout(120_000);
    const token = await getAccessToken(request);
    const models = await listChatModels(request, token);
    test.skip(models.length < 1, 'needs a chat model + provider stack');

    const session = await createChatSession(request, token, models[0].user_model_id, `E2E rack live ${Date.now()}`);
    try {
      await patchChatSession(request, token, session.session_id, { enabled_tools: ['find_tools'] });
      await loginViaUI(page);
      await page.goto(`/chat/${session.session_id}`);

      await expect(page.getByTestId('agent-rack-chip-tool-find_tools')).toBeVisible({ timeout: 15_000 });

      const textarea = page.getByRole('textbox').first();
      await textarea.fill('Say hi in one word.');
      await page.getByTitle('Send').click();

      const phase = page.getByTestId('agent-inspector-phase');
      await expect(phase).not.toHaveText('Idle', { timeout: 90_000 });
    } finally {
      await deleteChatSession(request, token, session.session_id).catch(() => {});
    }
  });
});
