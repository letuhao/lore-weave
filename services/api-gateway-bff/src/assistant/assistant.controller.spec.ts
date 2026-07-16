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
    process.env.CHAT_SERVICE_URL = 'http://chat:8090';
    controller = new AssistantController();
  });
  afterEach(() => {
    delete process.env.JWT_SECRET;
    delete process.env.BOOK_SERVICE_URL;
    delete process.env.KNOWLEDGE_SERVICE_URL;
    delete process.env.GLOSSARY_SERVICE_URL;
    delete process.env.AUTH_SERVICE_URL;
    delete process.env.INTERNAL_SERVICE_TOKEN;
    delete process.env.CHAT_SERVICE_URL;
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

describe('AssistantController — end-day (A1 public distill trigger)', () => {
  let controller: AssistantController;

  beforeEach(() => {
    process.env.JWT_SECRET = TEST_SECRET;
    process.env.INTERNAL_SERVICE_TOKEN = 'itok';
    process.env.CHAT_SERVICE_URL = 'http://chat:8090';
    controller = new AssistantController();
  });
  afterEach(() => {
    delete process.env.JWT_SECRET;
    delete process.env.INTERNAL_SERVICE_TOKEN;
    delete process.env.CHAT_SERVICE_URL;
    (global as any).fetch = undefined;
  });

  const validBody = { book_id: 'diary-1', model_source: 'user_model', model_ref: 'model-uuid-1' };

  it('401 on a missing bearer — never touches chat', async () => {
    const f = jest.fn();
    (global as any).fetch = f;
    await expectStatus(controller.endDay(validBody, undefined), 401);
    expect(f).not.toHaveBeenCalled();
  });

  it('400 when book_id / model_ref are missing — never touches chat', async () => {
    const f = jest.fn();
    (global as any).fetch = f;
    await expectStatus(controller.endDay({ book_id: 'diary-1' }, bearer('u1')), 400);
    expect(f).not.toHaveBeenCalled();
  });

  it('forwards to chat internal distill with the SERVER-DERIVED user_id + internal token, NO entry_date', async () => {
    const f = jest
      .fn()
      .mockResolvedValueOnce(resp(202, { enqueued: true, entry_date: '2026-07-12', message_id: '1-0' }));
    (global as any).fetch = f;

    const out = await controller.endDay(
      { ...validBody, language: 'vi', entry_zone: 'Asia/Ho_Chi_Minh' },
      bearer('user-42'),
    );

    expect(f).toHaveBeenCalledTimes(1);
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('http://chat:8090/internal/chat/assistant/distill');
    expect(init.method).toBe('POST');
    // Internal token, NOT the user JWT (parity with the ontology adopt).
    expect(init.headers['x-internal-token']).toBe('itok');
    expect(init.headers.authorization).toBeUndefined();
    const sent = JSON.parse(init.body);
    // user_id is server-derived from the token's sub, never a client field.
    expect(sent.user_id).toBe('user-42');
    expect(sent.book_id).toBe('diary-1');
    expect(sent.model_source).toBe('user_model');
    expect(sent.model_ref).toBe('model-uuid-1');
    expect(sent.language).toBe('vi');
    expect(sent.entry_zone).toBe('Asia/Ho_Chi_Minh');
    // D-R14 / LOW-4: the gateway must NOT forward a calendar day — chat stamps it server-side.
    expect(sent.entry_date).toBeUndefined();

    expect(out).toEqual({ enqueued: true, entry_date: '2026-07-12', message_id: '1-0' });
  });

  it('surfaces the downstream status (a 503 enqueue failure is not masked as 500)', async () => {
    (global as any).fetch = jest
      .fn()
      .mockResolvedValueOnce(resp(503, { detail: 'failed to enqueue distill: redis down' }));
    const err = await expectStatus(controller.endDay(validBody, bearer('u1')), 503);
    expect(err.getResponse()).toBe('failed to enqueue distill: redis down');
  });

  it('a 400 bad model_ref from chat surfaces as 400', async () => {
    (global as any).fetch = jest.fn().mockResolvedValueOnce(resp(400, { detail: 'unknown model_ref' }));
    await expectStatus(controller.endDay(validBody, bearer('u1')), 400);
  });
});

describe('AssistantController — correct (WS-2.6a / D17 memory amendment)', () => {
  let controller: AssistantController;

  beforeEach(() => {
    process.env.JWT_SECRET = TEST_SECRET;
    process.env.INTERNAL_SERVICE_TOKEN = 'itok';
    process.env.BOOK_SERVICE_URL = 'http://book:8205';
    process.env.CHAT_SERVICE_URL = 'http://chat:8090';
    controller = new AssistantController();
  });
  afterEach(() => {
    delete process.env.JWT_SECRET;
    delete process.env.INTERNAL_SERVICE_TOKEN;
    delete process.env.BOOK_SERVICE_URL;
    delete process.env.CHAT_SERVICE_URL;
    (global as any).fetch = undefined;
  });

  const validBody = {
    book_id: 'diary-1', chapter_id: 'ch-1', body: 'Alice froze the budget, not Minh.',
    model_source: 'user_model', model_ref: 'model-uuid-1',
  };

  it('401 on a missing bearer — never touches book or chat', async () => {
    const f = jest.fn();
    (global as any).fetch = f;
    await expectStatus(controller.correct(validBody, undefined), 401);
    expect(f).not.toHaveBeenCalled();
  });

  it('400 when a required field is missing — never touches book or chat', async () => {
    const f = jest.fn();
    (global as any).fetch = f;
    await expectStatus(controller.correct({ book_id: 'diary-1', chapter_id: 'ch-1' }, bearer('u1')), 400);
    expect(f).not.toHaveBeenCalled();
  });

  it('amends with the caller BEARER then reconciles with the internal token + amend entry_date', async () => {
    const f = jest
      .fn()
      // leg 1 — amend (user JWT, owner-gated server-side)
      .mockResolvedValueOnce(resp(200, { amended: true, entry_date: '2026-03-10', kept_preserved: true }))
      // legs 2+3 — reextract enqueue (internal token)
      .mockResolvedValueOnce(resp(202, { enqueued: true, entry_date: '2026-03-10', message_id: '9-0' }));
    (global as any).fetch = f;

    const out = await controller.correct({ ...validBody, language: 'vi' }, bearer('user-42'));

    expect(f).toHaveBeenCalledTimes(2);
    const [amendUrl, amendInit] = f.mock.calls[0];
    expect(amendUrl).toBe('http://book:8205/v1/books/diary-1/diary/entries/ch-1/amend');
    expect(amendInit.method).toBe('POST');
    // leg 1 carries the caller's JWT (owner-gated), NOT the internal token.
    expect(amendInit.headers.authorization).toMatch(/^Bearer /);
    expect(amendInit.headers['x-internal-token']).toBeUndefined();
    expect(JSON.parse(amendInit.body).body).toContain('Alice');

    const [reUrl, reInit] = f.mock.calls[1];
    expect(reUrl).toBe('http://chat:8090/internal/chat/assistant/reextract');
    // legs 2+3 carry the internal token + server-derived user_id + the amend's entry_date.
    expect(reInit.headers['x-internal-token']).toBe('itok');
    expect(reInit.headers.authorization).toBeUndefined();
    const sent = JSON.parse(reInit.body);
    expect(sent.user_id).toBe('user-42');
    expect(sent.book_id).toBe('diary-1');
    expect(sent.entry_date).toBe('2026-03-10'); // from the amend response, NOT a client day
    expect(sent.body).toContain('Alice');
    expect(sent.language).toBe('vi');

    expect(out).toEqual({
      amended: true, entry_date: '2026-03-10', kept_preserved: true,
      reextract_enqueued: true, message_id: '9-0',
    });
  });

  it('a failed amend fails the whole call — never enqueues a reconcile', async () => {
    const f = jest.fn().mockResolvedValueOnce(resp(403, { error: 'BOOK_FORBIDDEN' }));
    (global as any).fetch = f;
    await expectStatus(controller.correct(validBody, bearer('u1')), 403);
    expect(f).toHaveBeenCalledTimes(1); // only the amend was attempted
  });

  it('amend OK but reconcile enqueue fails → amended:true, reextract_enqueued:false (non-fatal)', async () => {
    const f = jest
      .fn()
      .mockResolvedValueOnce(resp(200, { amended: true, entry_date: '2026-03-10', kept_preserved: false }))
      .mockResolvedValueOnce(resp(503, { detail: 'failed to enqueue reextract: redis down' }));
    (global as any).fetch = f;

    const out = await controller.correct(validBody, bearer('u1'));
    // The SSOT correction stands; the reconcile is surfaced as retryable, not masked as success.
    expect(out.amended).toBe(true);
    expect(out.reextract_enqueued).toBe(false);
    expect(out.reextract_error).toContain('redis down');
  });
});

describe('AssistantController — forget (WS-2.6c / D17 forget-a-person)', () => {
  let controller: AssistantController;

  beforeEach(() => {
    process.env.JWT_SECRET = TEST_SECRET;
    process.env.INTERNAL_SERVICE_TOKEN = 'itok';
    process.env.BOOK_SERVICE_URL = 'http://book:8205';
    process.env.KNOWLEDGE_SERVICE_URL = 'http://knowledge:8210';
    controller = new AssistantController();
  });
  afterEach(() => {
    delete process.env.JWT_SECRET;
    delete process.env.INTERNAL_SERVICE_TOKEN;
    delete process.env.BOOK_SERVICE_URL;
    delete process.env.KNOWLEDGE_SERVICE_URL;
    (global as any).fetch = undefined;
  });

  const validBody = { book_id: 'diary-1', name: 'Minh' };

  it('401 on a missing bearer — never touches any service', async () => {
    const f = jest.fn();
    (global as any).fetch = f;
    await expectStatus(controller.forget(validBody, undefined), 401);
    expect(f).not.toHaveBeenCalled();
  });

  it('400 when book_id / name missing — never touches any service', async () => {
    const f = jest.fn();
    (global as any).fetch = f;
    await expectStatus(controller.forget({ book_id: 'diary-1' }, bearer('u1')), 400);
    expect(f).not.toHaveBeenCalled();
  });

  it('erases structured memory (internal token) then redacts the source (caller bearer)', async () => {
    const f = jest
      .fn()
      .mockResolvedValueOnce(resp(200, { forgotten: true, name: 'Minh', entities_deleted: 1,
        facts_deleted: 2, pending_tombstoned: 1 }))
      .mockResolvedValueOnce(resp(200, { redacted_entries: 2, name: 'Minh' }));
    (global as any).fetch = f;

    const out = await controller.forget(validBody, bearer('user-42'));

    expect(f).toHaveBeenCalledTimes(2);
    const [knUrl, knInit] = f.mock.calls[0];
    expect(knUrl).toBe('http://knowledge:8210/internal/admin/assistant/forget-entity');
    expect(knInit.headers['x-internal-token']).toBe('itok');
    expect(knInit.headers.authorization).toBeUndefined();
    expect(JSON.parse(knInit.body).user_id).toBe('user-42'); // server-derived

    const [bkUrl, bkInit] = f.mock.calls[1];
    expect(bkUrl).toBe('http://book:8205/v1/books/diary-1/diary/redact');
    expect(bkInit.headers.authorization).toMatch(/^Bearer /); // owner-gated by caller JWT
    expect(bkInit.headers['x-internal-token']).toBeUndefined();
    expect(JSON.parse(bkInit.body).name).toBe('Minh');

    expect(out).toEqual({
      forgotten: true, name: 'Minh', entities_deleted: 1, facts_deleted: 2,
      pending_tombstoned: 1, redacted_entries: 2,
    });
  });

  it('a failed structured erase fails the whole call — never redacts', async () => {
    const f = jest.fn().mockResolvedValueOnce(resp(502, { detail: 'neo4j down' }));
    (global as any).fetch = f;
    await expectStatus(controller.forget(validBody, bearer('u1')), 502);
    expect(f).toHaveBeenCalledTimes(1);
  });

  // A1.3 (SEC-1 regression guard) — the knowledge internal routes trust the `user_id` in their body, so
  // the gateway's whole tenancy guarantee is that this user_id comes from the JWT `sub`, NEVER from client
  // input. A forged `user_id` in the request body must be IGNORED — else user A could erase/forget across
  // to user B by resolving B's project. This test is the tripwire if a future edit starts reading it.
  it('IGNORES a forged user_id in the body — the internal call carries the JWT sub, not the attacker value', async () => {
    const f = jest
      .fn()
      .mockResolvedValueOnce(resp(200, { forgotten: true, name: 'Minh' }))
      .mockResolvedValueOnce(resp(200, { redacted_entries: 1, name: 'Minh' }));
    (global as any).fetch = f;

    // The attacker authenticates as user-42 but tries to smuggle victim-99 in the body.
    const forgedBody = { ...validBody, user_id: 'victim-99' } as any;
    await controller.forget(forgedBody, bearer('user-42'));

    const sentUserId = JSON.parse(f.mock.calls[0][1].body).user_id;
    expect(sentUserId).toBe('user-42'); // JWT sub wins
    expect(sentUserId).not.toBe('victim-99'); // the forged body value is dropped
  });

  it('structured erase OK but redaction fails → forgotten:true + redaction_error (non-fatal)', async () => {
    const f = jest
      .fn()
      .mockResolvedValueOnce(resp(200, { forgotten: true, name: 'Minh', entities_deleted: 1, facts_deleted: 2 }))
      .mockResolvedValueOnce(resp(500, { error: 'BOOK_CONFLICT' }));
    (global as any).fetch = f;
    const out = await controller.forget(validBody, bearer('u1'));
    expect(out.forgotten).toBe(true);
    expect(out.redacted_entries).toBeUndefined();
    expect(out.redaction_error).toContain('BOOK_CONFLICT');
  });
});

describe('AssistantController — new-epoch (WS-2.10 / T18 employment epoch)', () => {
  let controller: AssistantController;

  beforeEach(() => {
    process.env.JWT_SECRET = TEST_SECRET;
    process.env.INTERNAL_SERVICE_TOKEN = 'itok';
    process.env.KNOWLEDGE_SERVICE_URL = 'http://knowledge:8210';
    controller = new AssistantController();
  });
  afterEach(() => {
    delete process.env.JWT_SECRET;
    delete process.env.INTERNAL_SERVICE_TOKEN;
    delete process.env.KNOWLEDGE_SERVICE_URL;
    (global as any).fetch = undefined;
  });

  const validBody = { book_id: 'diary-1' };

  it('401 on a missing bearer — never touches knowledge', async () => {
    const f = jest.fn();
    (global as any).fetch = f;
    await expectStatus(controller.newEpoch(validBody, undefined), 401);
    expect(f).not.toHaveBeenCalled();
  });

  it('400 when book_id missing', async () => {
    const f = jest.fn();
    (global as any).fetch = f;
    await expectStatus(controller.newEpoch({}, bearer('u1')), 400);
    expect(f).not.toHaveBeenCalled();
  });

  it('closes the current epoch (internal token) then provisions a fresh project (bearer)', async () => {
    const f = jest
      .fn()
      .mockResolvedValueOnce(resp(200, { closed: true, project_id: 'proj-old', facts_invalidated: 7 }))
      .mockResolvedValueOnce(resp(200, { project_id: 'proj-new' }));
    (global as any).fetch = f;

    const out = await controller.newEpoch(validBody, bearer('user-42'));

    expect(f).toHaveBeenCalledTimes(2);
    const [closeUrl, closeInit] = f.mock.calls[0];
    expect(closeUrl).toBe('http://knowledge:8210/internal/admin/assistant/close-epoch');
    expect(closeInit.headers['x-internal-token']).toBe('itok');
    expect(JSON.parse(closeInit.body).user_id).toBe('user-42'); // server-derived

    const [projUrl, projInit] = f.mock.calls[1];
    expect(projUrl).toBe('http://knowledge:8210/v1/knowledge/projects/assistant');
    expect(projInit.headers.authorization).toMatch(/^Bearer /);

    expect(out).toEqual({
      epoch_closed: true, closed_project_id: 'proj-old', facts_invalidated: 7,
      new_project_id: 'proj-new', new_diary_volume: 'reused_book:fresh_project',
    });
  });

  it('a failed close fails the whole call — never provisions a new epoch', async () => {
    const f = jest.fn().mockResolvedValueOnce(resp(502, { detail: 'neo4j down' }));
    (global as any).fetch = f;
    await expectStatus(controller.newEpoch(validBody, bearer('u1')), 502);
    expect(f).toHaveBeenCalledTimes(1);
  });
});

describe('AssistantController — schedule (WS-3.2 opt-in toggle)', () => {
  let controller: AssistantController;

  beforeEach(() => {
    process.env.JWT_SECRET = TEST_SECRET;
    process.env.INTERNAL_SERVICE_TOKEN = 'itok';
    process.env.SCHEDULER_SERVICE_URL = 'http://scheduler:8095';
    controller = new AssistantController();
  });
  afterEach(() => {
    delete process.env.JWT_SECRET;
    delete process.env.INTERNAL_SERVICE_TOKEN;
    delete process.env.SCHEDULER_SERVICE_URL;
    (global as any).fetch = undefined;
  });

  it('401 on a missing bearer — never touches the scheduler', async () => {
    const f = jest.fn();
    (global as any).fetch = f;
    await expectStatus(controller.schedule({ job_kind: 'eod_distill', enabled: true }, undefined), 401);
    expect(f).not.toHaveBeenCalled();
  });

  it('400 on an unknown job_kind — never touches the scheduler', async () => {
    const f = jest.fn();
    (global as any).fetch = f;
    await expectStatus(controller.schedule({ job_kind: 'nope', enabled: true }, bearer('u1')), 400);
    expect(f).not.toHaveBeenCalled();
  });

  it('PUTs to scheduler with the SERVER-DERIVED user_id + internal token', async () => {
    const f = jest.fn().mockResolvedValueOnce(resp(200, { enabled: true, next_fire_at: '2026-07-16T21:00:00Z' }));
    (global as any).fetch = f;
    const out = await controller.schedule(
      { job_kind: 'eod_distill', cadence: 'daily', fire_local_time: '21:00', timezone: 'UTC', enabled: true },
      bearer('user-42'),
    );
    expect(f).toHaveBeenCalledTimes(1);
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('http://scheduler:8095/internal/schedules');
    expect(init.method).toBe('PUT');
    expect(init.headers['x-internal-token']).toBe('itok');
    expect(init.headers.authorization).toBeUndefined();
    const sent = JSON.parse(init.body);
    expect(sent.user_id).toBe('user-42'); // from the JWT sub, never a body field
    expect(sent.job_kind).toBe('eod_distill');
    expect(sent.enabled).toBe(true);
    expect(out).toEqual({ enabled: true, next_fire_at: '2026-07-16T21:00:00Z' });
  });
});

describe('AssistantController — erase (D-R27 row-delete erasure)', () => {
  let controller: AssistantController;

  beforeEach(() => {
    process.env.JWT_SECRET = TEST_SECRET;
    process.env.INTERNAL_SERVICE_TOKEN = 'itok';
    process.env.BOOK_SERVICE_URL = 'http://book:8205';
    process.env.KNOWLEDGE_SERVICE_URL = 'http://knowledge:8210';
    process.env.GLOSSARY_SERVICE_URL = 'http://glossary:8203';
    process.env.CHAT_SERVICE_URL = 'http://chat:8090';
    controller = new AssistantController();
  });
  afterEach(() => {
    delete process.env.JWT_SECRET;
    delete process.env.INTERNAL_SERVICE_TOKEN;
    delete process.env.BOOK_SERVICE_URL;
    delete process.env.KNOWLEDGE_SERVICE_URL;
    delete process.env.GLOSSARY_SERVICE_URL;
    delete process.env.CHAT_SERVICE_URL;
    (global as any).fetch = undefined;
  });

  it('401 on a missing bearer — never touches any service', async () => {
    const f = jest.fn();
    (global as any).fetch = f;
    await expectStatus(controller.eraseData(undefined), 401);
    expect(f).not.toHaveBeenCalled();
  });

  it('resolves the diary (any lifecycle, no create), then hard-deletes source-first across the services with internal token + server-derived id', async () => {
    const f = jest
      .fn()
      .mockResolvedValueOnce(resp(200, { book_id: 'diary-1', lifecycle: 'active' })) // 1. GET resolver
      .mockResolvedValueOnce(resp(200, { deleted_sessions: 1 })) // 2. chat erase (SOURCE, book_id=None)
      .mockResolvedValueOnce(resp(200, { projects_erased: 1, passages_deleted: 12 })) // 3. knowledge (by user_id)
      .mockResolvedValueOnce(resp(200, { erased: true, deleted_books: 1 })) // 4. book erase (SOURCE + gate)
      .mockResolvedValueOnce(resp(200, { deleted_entities: 5 })); // 5. glossary erase (gated by bookErased)
    (global as any).fetch = f;

    const out = await controller.eraseData(bearer('user-42'));

    expect(f).toHaveBeenCalledTimes(5);
    // 1. Resolve diary via the READ-ONLY internal resolver (any lifecycle, never creates), internal token.
    expect(f.mock.calls[0][0]).toBe('http://book:8205/internal/books/diary?user_id=user-42');
    expect(f.mock.calls[0][1].headers['x-internal-token']).toBe('itok');
    // 2. SOURCE first: chat by user_id ONLY (book_id=None → ALL assistant sessions).
    expect(f.mock.calls[1][0]).toBe('http://chat:8090/internal/chat/assistant/data?user_id=user-42');
    expect(f.mock.calls[1][0]).not.toContain('book_id');
    expect(f.mock.calls[1][1].method).toBe('DELETE');
    // 3. DERIVED knowledge erase by USER_ID ONLY (audit HIGH-2) — knowledge-service resolves the
    //    assistant project(s) internally by is_assistant, so it never depends on the book still existing
    //    and no longer needs a separate book-keyed project resolution.
    expect(f.mock.calls[2][0]).toBe('http://knowledge:8210/internal/admin/assistant/erase?user_id=user-42');
    expect(f.mock.calls[2][0]).not.toContain('project_id');
    expect(f.mock.calls[2][1].headers['x-internal-token']).toBe('itok');
    // 4. book erase (source + ownership gate).
    expect(f.mock.calls[3][0]).toBe('http://book:8205/internal/books/diary-1/diary/erase?user_id=user-42');
    // 5. glossary LAST (derived), gated by the book erase confirming ownership.
    expect(f.mock.calls[4][0]).toBe('http://glossary:8203/internal/books/diary-1/entities');
    expect(f.mock.calls[4][1].headers['x-internal-token']).toBe('itok');
    expect(f.mock.calls[4][1].headers.authorization).toBeUndefined();

    expect(out.erased).toBe(true);
    expect(out.book_id).toBe('diary-1');
    expect(out.deleted.diary_book).toEqual({ erased: true, deleted_books: 1 });
  });

  it('a TRASHED diary is still erased (resolver returns it — no silent no-op)', async () => {
    const f = jest
      .fn()
      .mockResolvedValueOnce(resp(200, { book_id: 'diary-1', lifecycle: 'trashed' })) // resolver returns trashed
      .mockResolvedValueOnce(resp(200, { deleted_sessions: 1 })) // chat
      .mockResolvedValueOnce(resp(200, { projects_erased: 1, passages_deleted: 3 })) // knowledge (by user_id)
      .mockResolvedValueOnce(resp(200, { erased: true, deleted_books: 1 })) // book erase
      .mockResolvedValueOnce(resp(200, { deleted_entities: 2 })); // glossary
    (global as any).fetch = f;
    const out = await controller.eraseData(bearer('u1'));
    expect(out.erased).toBe(true); // trashed diary was NOT a silent no-op
    expect(f).toHaveBeenCalledTimes(5);
  });

  it('a partial failure (glossary leg errors) reports erased:false — never a false "your data is gone"', async () => {
    const f = jest
      .fn()
      .mockResolvedValueOnce(resp(200, { book_id: 'diary-1' }))
      .mockResolvedValueOnce(resp(200, { deleted_sessions: 1 })) // chat
      .mockResolvedValueOnce(resp(200, { projects_erased: 1, passages_deleted: 3 })) // knowledge (by user_id)
      .mockResolvedValueOnce(resp(200, { erased: true, deleted_books: 1 })) // book erase
      .mockResolvedValueOnce(resp(500, { error: 'glossary down' })); // glossary FAILS
    (global as any).fetch = f;
    const out = await controller.eraseData(bearer('u1'));
    expect(out.erased).toBe(false); // aggregate: a failed leg means NOT fully erased
  });

  it('audit HIGH-2: knowledge erase (diary text) FAILING reports erased:false even though chat+book succeed', async () => {
    // The regression the audit caught: the KG leg holds decryptable diary passages + fact text. A KG
    // failure must NOT be masked as erased:true. (Previously the KG leg was skipped-without-failing when
    // a book-keyed project resolution failed.)
    const f = jest
      .fn()
      .mockResolvedValueOnce(resp(200, { book_id: 'diary-1' }))
      .mockResolvedValueOnce(resp(200, { deleted_sessions: 1 })) // chat OK
      .mockResolvedValueOnce(resp(503, { error: 'knowledge down' })) // knowledge FAILS
      .mockResolvedValueOnce(resp(200, { erased: true, deleted_books: 1 })) // book OK
      .mockResolvedValueOnce(resp(200, { deleted_entities: 2 })); // glossary OK
    (global as any).fetch = f;
    const out = await controller.eraseData(bearer('u1'));
    expect(out.erased).toBe(false); // a surviving diary-text store means NOT erased
  });

  it('audit HIGH-2: no diary book, but orphaned assistant knowledge is STILL erased by user_id', async () => {
    // The other half of HIGH-2: a user whose diary book was hard-deleted out-of-band still has assistant
    // KG passages + pending/rejected fact text. The knowledge erase runs by user_id, so it is reached.
    const f = jest
      .fn()
      .mockResolvedValueOnce(resp(404, { error: 'no diary for user' })) // resolver 404 (book gone)
      .mockResolvedValueOnce(resp(200, { deleted_sessions: 0 })) // chat
      .mockResolvedValueOnce(resp(200, { projects_erased: 1, passages_deleted: 4 })); // knowledge STILL runs
    (global as any).fetch = f;
    const out = await controller.eraseData(bearer('u1'));
    expect(f).toHaveBeenCalledTimes(3); // resolver + chat + KNOWLEDGE (no book/glossary — no diary)
    expect(f.mock.calls[2][0]).toBe('http://knowledge:8210/internal/admin/assistant/erase?user_id=u1');
    expect(out.erased).toBe(true); // all attempted legs (chat + knowledge) succeeded
    expect(out.book_id).toBeUndefined();
  });

  // C8 / SD-C8 — the reflection-dismiss route. The SEC-1 property: the owner is derived from the JWT
  // `sub`, NEVER from the client body (a client that sends owner_user_id must not dismiss for another user).
  it('reflection-dismiss: forwards owner_user_id = JWT sub (never the client body) to chat', async () => {
    const f = jest.fn().mockResolvedValueOnce(resp(200, { dismissed: true }));
    (global as any).fetch = f;
    // a malicious client tries to smuggle owner_user_id 'victim' — the BFF must ignore it.
    const out = await controller.reflectionDismiss(
      { pattern_key: 'co_occurrence:migration', owner_user_id: 'victim' } as any,
      bearer('attacker'),
    );
    expect(out).toEqual({ dismissed: true, pattern_key: 'co_occurrence:migration' });
    expect(f).toHaveBeenCalledTimes(1);
    expect(f.mock.calls[0][0]).toBe('http://chat:8090/internal/chat/assistant/reflection-dismiss');
    const sent = JSON.parse(f.mock.calls[0][1].body);
    expect(sent.owner_user_id).toBe('attacker'); // the JWT sub, NOT the client-sent 'victim'
    expect(sent.pattern_key).toBe('co_occurrence:migration');
  });

  it('reflection-dismiss: 401 on a missing token — no fan-out', async () => {
    const f = jest.fn();
    (global as any).fetch = f;
    await expectStatus(controller.reflectionDismiss({ pattern_key: 'x' }, undefined), 401);
    expect(f).not.toHaveBeenCalled();
  });

  it('reflection-dismiss: 400 on an empty pattern_key — no downstream call', async () => {
    const f = jest.fn();
    (global as any).fetch = f;
    await expectStatus(controller.reflectionDismiss({ pattern_key: '  ' }, bearer('u1')), 400);
    expect(f).not.toHaveBeenCalled();
  });
});
