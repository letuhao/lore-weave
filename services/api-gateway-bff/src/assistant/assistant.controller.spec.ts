import * as jwt from 'jsonwebtoken';
import { HttpException } from '@nestjs/common';

import { AssistantController } from './assistant.controller';

const TEST_SECRET = 'assistant-provision-test-secret-32ch!';
const WORK_KINDS_EXPECTED = ['colleague', 'project', 'meeting', 'decision', 'task', 'jargon', 'org'];

function bearer(sub: string): string {
  // exp is REQUIRED by the controller (parity with the downstream services).
  return `Bearer ${jwt.sign({ sub }, TEST_SECRET, { expiresIn: '1h' })}`;
}

function resp(status: number, bodyObj: unknown) {
  return { ok: status >= 200 && status < 300, status, text: async () => JSON.stringify(bodyObj) };
}

async function expectStatus(p: Promise<unknown>, status: number): Promise<HttpException> {
  try {
    await p;
  } catch (e) {
    expect(e).toBeInstanceOf(HttpException);
    expect((e as HttpException).getStatus()).toBe(status);
    return e as HttpException;
  }
  throw new Error(`expected an HttpException with status ${status}`);
}

describe('AssistantController (WS-1.4 provisioning orchestrator)', () => {
  let controller: AssistantController;

  beforeEach(() => {
    process.env.JWT_SECRET = TEST_SECRET;
    process.env.BOOK_SERVICE_URL = 'http://book:8205';
    process.env.KNOWLEDGE_SERVICE_URL = 'http://knowledge:8210';
    process.env.GLOSSARY_SERVICE_URL = 'http://glossary:8203';
    process.env.AUTH_SERVICE_URL = 'http://auth:8201';
    process.env.INTERNAL_SERVICE_TOKEN = 'itok';
    controller = new AssistantController();
  });
  afterEach(() => {
    delete process.env.JWT_SECRET;
    delete process.env.BOOK_SERVICE_URL;
    delete process.env.KNOWLEDGE_SERVICE_URL;
    delete process.env.GLOSSARY_SERVICE_URL;
    delete process.env.AUTH_SERVICE_URL;
    delete process.env.INTERNAL_SERVICE_TOKEN;
    (global as any).fetch = undefined;
  });

  it('401 on a missing bearer token — no fan-out', async () => {
    const f = jest.fn();
    (global as any).fetch = f;
    await expectStatus(controller.provision({}, undefined), 401);
    expect(f).not.toHaveBeenCalled();
  });

  it('401 on an invalid JWT — no fan-out', async () => {
    const f = jest.fn();
    (global as any).fetch = f;
    await expectStatus(controller.provision({}, 'Bearer not-a-jwt'), 401);
    expect(f).not.toHaveBeenCalled();
  });

  it('401 on an expiry-less token (exp is required) — no fan-out', async () => {
    const f = jest.fn();
    (global as any).fetch = f;
    const noExp = `Bearer ${jwt.sign({ sub: 'u1' }, TEST_SECRET)}`; // no expiresIn
    await expectStatus(controller.provision({}, noExp), 401);
    expect(f).not.toHaveBeenCalled();
  });

  it('provisions the diary + assistant project + work ontology + self-entity, forwarding correctly', async () => {
    const f = jest
      .fn()
      .mockResolvedValueOnce(resp(201, { book_id: 'diary-1' }))
      .mockResolvedValueOnce(resp(201, { project_id: 'proj-1' }))
      .mockResolvedValueOnce(resp(200, { book_id: 'diary-1', adopted: WORK_KINDS_EXPECTED }))
      .mockResolvedValueOnce(resp(200, { display_name: 'Alex Kim' })) // auth profile GET
      .mockResolvedValueOnce(resp(201, { entity_id: 'self-1', created: true })); // self-entity POST
    (global as any).fetch = f;

    const out = await controller.provision({ title: 'My Journal' }, bearer('user-42'));

    expect(f).toHaveBeenCalledTimes(5);
    // Step 1 → book-service diary get-or-create, with the user's Bearer.
    const [bookUrl, bookInit] = f.mock.calls[0];
    expect(bookUrl).toBe('http://book:8205/v1/books/diary');
    expect(bookInit.headers.authorization).toBe(bearer('user-42'));
    // Step 2 → knowledge assistant-project, bound to the diary the first step returned.
    const [kUrl, kInit] = f.mock.calls[1];
    expect(kUrl).toBe('http://knowledge:8210/v1/knowledge/projects/assistant');
    expect(JSON.parse(kInit.body)).toEqual({ book_id: 'diary-1' });
    // Step 3 → glossary adopt-kinds: a token-gated INTERNAL call (service token, not the user
    // JWT), user_id server-derived from the token's sub, body = the 7 work-kind codes.
    const [gUrl, gInit] = f.mock.calls[2];
    expect(gUrl).toBe('http://glossary:8203/internal/books/diary-1/ontology/adopt-kinds?user_id=user-42');
    expect(gInit.headers['x-internal-token']).toBe('itok');
    expect(gInit.headers.authorization).toBeUndefined(); // the user JWT is NOT forwarded internally
    expect(JSON.parse(gInit.body)).toEqual({ kinds: WORK_KINDS_EXPECTED });
    // Step 4 → auth profile GET (internal) for the display name.
    const [pUrl, pInit] = f.mock.calls[3];
    expect(pUrl).toBe('http://auth:8201/internal/users/user-42/profile');
    expect(pInit.method).toBe('GET');
    expect(pInit.headers['x-internal-token']).toBe('itok');
    // Step 5 → glossary self-entity POST with the fetched name.
    const [sUrl, sInit] = f.mock.calls[4];
    expect(sUrl).toBe('http://glossary:8203/internal/books/diary-1/self-entity?user_id=user-42');
    expect(sInit.headers['x-internal-token']).toBe('itok');
    expect(JSON.parse(sInit.body)).toEqual({ name: 'Alex Kim' });

    expect(out.provisioned).toBe(true);
    expect(out.book_id).toBe('diary-1');
    expect(out.project_id).toBe('proj-1');
    expect(out.provision_status.diary_book).toBe('ok');
    expect(out.provision_status.assistant_project).toBe('ok');
    expect(out.provision_status.work_ontology).toBe('ok');
    expect(out.provision_status.self_entity).toBe('ok');
    // Steps that depend on unbuilt slices are surfaced, never silently claimed done.
    expect(out.provision_status.consent).toBe('pending:user_opt_in');
    expect(out.provision_status.timezone).toBe('pending:user_confirm');
  });

  it('is idempotent-friendly: a 200 (existing) diary + project + adopt + self still provisions', async () => {
    const f = jest
      .fn()
      .mockResolvedValueOnce(resp(200, { book_id: 'diary-1' }))
      .mockResolvedValueOnce(resp(200, { project_id: 'proj-1' }))
      .mockResolvedValueOnce(resp(200, { adopted: WORK_KINDS_EXPECTED }))
      .mockResolvedValueOnce(resp(200, { display_name: 'Alex' }))
      .mockResolvedValueOnce(resp(200, { entity_id: 'self-1', created: false }));
    (global as any).fetch = f;
    const out = await controller.provision({}, bearer('u1'));
    expect(out.provisioned).toBe(true);
    expect(out.book_id).toBe('diary-1');
    expect(out.provision_status.work_ontology).toBe('ok');
    expect(out.provision_status.self_entity).toBe('ok');
  });

  it('an adopt failure is a recorded half-state — the durable core is still provisioned', async () => {
    const f = jest
      .fn()
      .mockResolvedValueOnce(resp(201, { book_id: 'diary-1' }))
      .mockResolvedValueOnce(resp(201, { project_id: 'proj-1' }))
      .mockResolvedValueOnce(resp(500, { error: 'GLOSS_INTERNAL' })) // adopt fails
      .mockResolvedValueOnce(resp(200, { display_name: 'Alex' })) // self-entity still runs (binds to the diary)
      .mockResolvedValueOnce(resp(201, { entity_id: 'self-1', created: true }));
    (global as any).fetch = f;
    const out = await controller.provision({}, bearer('u1'));
    // diary + project are the durable core → still provisioned; ontology re-drives next open.
    expect(out.provisioned).toBe(true);
    expect(out.provision_status.work_ontology).toBe('error:500');
    expect(out.provision_status.self_entity).toBe('ok');
  });

  it('missing glossary config → work_ontology error:not_configured (no crash, core still ok)', async () => {
    delete process.env.GLOSSARY_SERVICE_URL;
    const f = jest
      .fn()
      .mockResolvedValueOnce(resp(201, { book_id: 'diary-1' }))
      .mockResolvedValueOnce(resp(201, { project_id: 'proj-1' }));
    (global as any).fetch = f;
    const out = await controller.provision({}, bearer('u1'));
    expect(f).toHaveBeenCalledTimes(2); // adopt + self-entity never attempted (no glossary URL)
    expect(out.provisioned).toBe(true);
    expect(out.provision_status.work_ontology).toBe('error:not_configured');
    expect(out.provision_status.self_entity).toBe('error:not_configured');
  });

  it('a TRASHED diary is surfaced and the project is NOT attempted', async () => {
    const f = jest.fn().mockResolvedValueOnce(resp(409, { code: 'BOOK_DIARY_TRASHED', message: 'in trash' }));
    (global as any).fetch = f;

    const out = await controller.provision({}, bearer('u1'));

    expect(f).toHaveBeenCalledTimes(1); // never forked a fresh diary, never touched knowledge
    expect(out.provisioned).toBe(false);
    expect(out.provision_status.diary_book).toBe('trashed');
    expect(out.provision_status.assistant_project).toBe('skipped:no_diary');
  });

  it('a diary failure aborts before the project step (the diary is the anchor)', async () => {
    const f = jest.fn().mockResolvedValueOnce(resp(500, { code: 'BOOK_CONFLICT' }));
    (global as any).fetch = f;
    const out = await controller.provision({}, bearer('u1'));
    expect(f).toHaveBeenCalledTimes(1);
    expect(out.provisioned).toBe(false);
    expect(out.provision_status.diary_book).toBe('error:500');
    expect(out.provision_status.assistant_project).toBe('skipped:no_diary');
  });

  it('a project failure leaves a visible half-state (diary ok, project error) — not a crash', async () => {
    const f = jest
      .fn()
      .mockResolvedValueOnce(resp(201, { book_id: 'diary-1' }))
      .mockResolvedValueOnce(resp(503, { detail: 'knowledge down' }))
      .mockResolvedValueOnce(resp(200, { adopted: WORK_KINDS_EXPECTED })) // adopt still runs (binds to the diary)
      .mockResolvedValueOnce(resp(200, { display_name: 'Alex' })) // profile
      .mockResolvedValueOnce(resp(201, { entity_id: 'self-1', created: true })); // self-entity still runs
    (global as any).fetch = f;

    const out = await controller.provision({}, bearer('u1'));

    expect(out.provisioned).toBe(false); // core not complete
    expect(out.book_id).toBe('diary-1'); // the anchor exists
    expect(out.provision_status.diary_book).toBe('ok');
    expect(out.provision_status.assistant_project).toBe('error:503');
    expect(out.provision_status.work_ontology).toBe('ok'); // ontology + self bind to the diary regardless
    expect(out.provision_status.self_entity).toBe('ok');
  });

  it('a transport failure on the diary step is a recorded half-state (status 0), not a throw', async () => {
    (global as any).fetch = jest.fn().mockRejectedValue(new Error('ECONNREFUSED'));
    const out = await controller.provision({}, bearer('u1'));
    expect(out.provisioned).toBe(false);
    expect(out.provision_status.diary_book).toBe('error:0');
    expect(out.provision_status.self_entity).toBe('skipped:no_diary');
  });
});
