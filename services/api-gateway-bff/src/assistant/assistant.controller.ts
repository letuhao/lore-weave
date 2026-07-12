// WS-1.4 — the Work Assistant provisioning orchestrator (spec 02 §Q2).
//
// This is the FIRST fan-out handler in the BFF (everything else is reverse-proxy). It
// provisions the assistant by calling the PUBLIC service APIs with the USER'S OWN JWT —
// so every downstream route owner-keys/grant-checks the caller itself, and we invent no new
// internal write surface (book-service /internal is read-only).
//
// Trust model (mirrors ToolsController): the FE presents its Bearer JWT; we validate it here
// and derive the identity from `sub` (SEC-1 — identity is NEVER a client body field). We then
// forward that SAME Bearer to the public endpoints.
//
// Partial-failure is a first-class outcome (T39): convergence-under-concurrency is not
// atomicity-under-failure. We return a `provision_status` the home strip reads and re-drives
// on every /assistant open, rather than pretending an all-or-nothing transaction across four
// services. The diary book is the ANCHOR (everything binds to it); if it cannot be made,
// nothing else is attempted.
//
// Scope note: this wires the two DURABLE cross-service resources whose idempotent get-or-create
// endpoints exist today — the diary book (WS-1.4a) and the assistant knowledge project
// (WS-1.4b). "Today's session" is created by the ChatView on first open (it, not the server,
// knows the user's chosen model); the self-entity (WS-1.5), consent opt-in, and timezone
// confirm (D9) are surfaced as explicit PENDING steps — never silently omitted, never
// auto-enabled.

import { Body, Controller, Delete, Headers, HttpException, Logger, Post } from '@nestjs/common';
import * as jwt from 'jsonwebtoken';

interface ProvisionBody {
  title?: string;
}

interface ProvisionStatus {
  diary_book: string; // 'ok' | 'trashed' | 'error:<status>'
  assistant_project: string; // 'ok' | 'skipped:no_diary' | 'error:<status>'
  work_ontology: string; // 'ok' | 'skipped:no_diary' | 'error:<status>' (WS-1.5b — clone work kinds into the diary)
  // Steps that depend on not-yet-built slices — surfaced, never silently dropped:
  todays_session: string; // the ChatView creates it on first open (needs the user's model)
  self_entity: string; // 'ok' | 'skipped:no_diary' | 'error:<status>' (WS-1.6 — seed the is_self identity)
  consent: string; // user opt-in only — NEVER auto-enabled as a provisioning side effect
  timezone: string; // D9 — explicit user confirm, never auto-set from the client zone
}

// WS-1.5 §Q2 — the System-tier work kinds cloned into the diary's book tier at provisioning.
const WORK_KINDS = ['colleague', 'project', 'meeting', 'decision', 'task', 'jargon', 'org'];

interface ProvisionResult {
  provisioned: boolean; // the durable core (diary + assistant project) is ready
  book_id?: string;
  project_id?: string;
  provision_status: ProvisionStatus;
}

// A1 / WS-1.10 — the public "End my day" trigger body. The FE supplies the diary book + the
// distill model (Q8 server-side model resolution is a follow-up). `entry_date` is DELIBERATELY
// NOT accepted here: the chat internal route stamps today server-side (D-R14 / internal.py LOW-4 —
// a client-controlled calendar day could overwrite/mis-bucket a historical entry).
interface EndDayBody {
  book_id?: string;
  model_source?: string;
  model_ref?: string;
  language?: string;
  entry_zone?: string;
}

interface EndDayResult {
  enqueued: boolean;
  entry_date?: string;
  message_id?: string;
}

// D-R27 (human-authorized) — the immediate-row-delete erasure result. Per-service delete counts so
// the caller can prove "row gone". Backup-resistant crypto-shred stays a separate goal (P-12).
interface EraseResult {
  erased: boolean;
  book_id?: string;
  deleted: {
    diary_book?: unknown;
    chat_sessions?: unknown;
    knowledge?: unknown;
    glossary?: unknown;
  };
}

const PROVISION_STEP_TIMEOUT_MS = 15_000;

@Controller('v1/assistant')
export class AssistantController {
  private readonly logger = new Logger(AssistantController.name);

  @Post('provision')
  async provision(
    @Body() body: ProvisionBody,
    @Headers('authorization') authorization?: string,
  ): Promise<ProvisionResult> {
    // 1. Authenticate — validate the user's JWT; identity is server-derived from `sub` (SEC-1).
    const { userId, token } = this.requireAuth(authorization);

    const bookUrl = process.env.BOOK_SERVICE_URL;
    const knowledgeUrl = process.env.KNOWLEDGE_SERVICE_URL;
    if (!bookUrl || !knowledgeUrl) {
      this.logger.error('assistant-provision rejected: BOOK/KNOWLEDGE service URL not configured');
      throw new HttpException('server_error', 500);
    }

    const authHeader = `Bearer ${token}`;
    const status: ProvisionStatus = {
      diary_book: 'pending',
      assistant_project: 'pending',
      work_ontology: 'pending',
      todays_session: 'deferred:created_on_first_open',
      self_entity: 'pending:WS-1.5',
      consent: 'pending:user_opt_in',
      timezone: 'pending:user_confirm',
    };

    // 2. Diary book (the anchor) — idempotent get-or-create.
    const diary = await this.postJson(`${bookUrl}/v1/books/diary`, authHeader, {
      title: body?.title,
    });
    if (diary.ok && typeof diary.body?.book_id === 'string') {
      status.diary_book = 'ok';
    } else if (diary.status === 409 && diary.body?.code === 'BOOK_DIARY_TRASHED') {
      // E14 — a trashed diary must be resolved by the user (restore vs start fresh) before
      // we provision anything onto it. Surface it; do not fork or resurrect.
      status.diary_book = 'trashed';
      status.assistant_project = 'skipped:no_diary';
      status.work_ontology = 'skipped:no_diary';
      status.self_entity = 'skipped:no_diary';
      return { provisioned: false, provision_status: status };
    } else {
      status.diary_book = `error:${diary.status}`;
      status.assistant_project = 'skipped:no_diary';
      status.work_ontology = 'skipped:no_diary';
      status.self_entity = 'skipped:no_diary';
      return { provisioned: false, provision_status: status };
    }
    const bookId: string = diary.body.book_id;

    // 3. Assistant knowledge project — bound to the diary, idempotent.
    const proj = await this.postJson(
      `${knowledgeUrl}/v1/knowledge/projects/assistant`,
      authHeader,
      { book_id: bookId },
    );
    let projectId: string | undefined;
    if (proj.ok && typeof proj.body?.project_id === 'string') {
      status.assistant_project = 'ok';
      projectId = proj.body.project_id;
    } else {
      // The diary exists but the project failed — a real, visible half-state (T39). The home
      // strip re-drives on the next open; this get-or-create is idempotent, so the retry is safe.
      status.assistant_project = `error:${proj.status}`;
    }

    // 4. Work ontology (WS-1.5 §Q2) — clone the System-tier work kinds into the diary's book
    //    tier so capture has them. A token-gated INTERNAL glossary call (a system op, not a
    //    user-authored write); ownership was already established when book-service created the
    //    diary under the user's JWT above, which is why adopt-kinds needs no further grant check.
    //    Idempotent + re-drivable, so a failure is a recorded half-state, never a hard error.
    const glossaryUrl = process.env.GLOSSARY_SERVICE_URL;
    const internalToken = process.env.INTERNAL_SERVICE_TOKEN;
    if (!glossaryUrl || !internalToken) {
      status.work_ontology = 'error:not_configured';
    } else {
      const adopt = await this.postInternal(
        `${glossaryUrl}/internal/books/${bookId}/ontology/adopt-kinds?user_id=${encodeURIComponent(userId)}`,
        internalToken,
        { kinds: WORK_KINDS },
      );
      status.work_ontology = adopt.ok ? 'ok' : `error:${adopt.status}`;
    }

    // 5. Self entity (WS-1.6 §Q5) — seed the user's OWN identity entity in the diary, marked
    //    is_self, so capture dedups the user's name onto it (they are not a colleague) and the
    //    detectors can exclude it. Needs the display name (from the auth profile). Best-effort +
    //    re-drivable, like the ontology; it depends on the diary + the adopted 'colleague' kind.
    const authUrl = process.env.AUTH_SERVICE_URL;
    if (!glossaryUrl || !internalToken || !authUrl) {
      status.self_entity = 'error:not_configured';
    } else {
      const profile = await this.getInternal(
        `${authUrl}/internal/users/${encodeURIComponent(userId)}/profile`,
        internalToken,
      );
      const name =
        profile.ok && typeof profile.body?.display_name === 'string' ? profile.body.display_name : '';
      // name may be '' (profile unreachable) — the glossary endpoint defaults it to "Me", so
      // the self-entity is still seeded (the user can rename it); the flag is what matters.
      const self = await this.postInternal(
        `${glossaryUrl}/internal/books/${bookId}/self-entity?user_id=${encodeURIComponent(userId)}`,
        internalToken,
        { name },
      );
      status.self_entity = self.ok ? 'ok' : `error:${self.status}`;
    }

    return {
      provisioned: status.diary_book === 'ok' && status.assistant_project === 'ok',
      book_id: bookId,
      project_id: projectId,
      provision_status: status,
    };
  }

  // A1 / WS-1.10 — the public "End my day" trigger. The FE cannot call chat-service's
  // X-Internal-Token-only `/internal/chat/assistant/distill` directly, so the BFF fronts it:
  // validate the user's JWT, derive `user_id` from `sub` (SEC-1 — never a body field), and forward
  // to the internal distill enqueue with the platform token. entry_date is OMITTED so chat stamps
  // today server-side (D-R14). Returns the 202 enqueue result (entry_date + message_id) so the FE
  // can poll for the day's diary entry to review.
  @Post('end-day')
  async endDay(
    @Body() body: EndDayBody,
    @Headers('authorization') authorization?: string,
  ): Promise<EndDayResult> {
    const { userId } = this.requireAuth(authorization);

    const bookId = (body?.book_id ?? '').trim();
    const modelSource = (body?.model_source ?? '').trim();
    const modelRef = (body?.model_ref ?? '').trim();
    if (!bookId || !modelSource || !modelRef) {
      throw new HttpException('book_id, model_source and model_ref are required', 400);
    }

    const chatUrl = process.env.CHAT_SERVICE_URL;
    const internalToken = process.env.INTERNAL_SERVICE_TOKEN;
    if (!chatUrl || !internalToken) {
      this.logger.error('assistant-end-day rejected: CHAT_SERVICE_URL / INTERNAL_SERVICE_TOKEN not configured');
      throw new HttpException('server_error', 500);
    }

    // Forward with the SERVER-DERIVED user_id + the platform token. No entry_date → chat defaults
    // to today in entry_zone (server-authoritative day bucketing, D-R14).
    const distill = await this.postInternal(
      `${chatUrl}/internal/chat/assistant/distill`,
      internalToken,
      {
        user_id: userId,
        book_id: bookId,
        model_source: modelSource,
        model_ref: modelRef,
        language: (body?.language ?? 'en').trim() || 'en',
        entry_zone: (body?.entry_zone ?? 'UTC').trim() || 'UTC',
      },
    );
    if (!distill.ok) {
      // Surface the real downstream status (400 bad model_ref, 503 enqueue failure) rather than a
      // blanket 500, so the home strip can tell "retry" from "fix your model".
      const detail =
        (typeof distill.body?.detail === 'string' && distill.body.detail) ||
        'failed to enqueue end-of-day distill';
      throw new HttpException(detail, distill.status >= 400 ? distill.status : 502);
    }
    return {
      enqueued: distill.body?.enqueued === true,
      entry_date: distill.body?.entry_date,
      message_id: distill.body?.message_id,
    };
  }

  // D-R27 (human-authorized) — the ASSISTANT DATA ERASURE. Immediate ROW-DELETE (not soft-trash) of
  // the user's whole diary footprint across four services, so the diary content is genuinely gone AND
  // a re-index cannot resurrect it (the distiller's SOURCE — the assistant chat messages — is deleted,
  // so a re-distill of any day finds nothing). Backup-resistant crypto-shred stays P-12.
  //
  // SEC-1: identity is server-derived from the JWT, and the diary book + assistant project are
  // RESOLVED SERVER-SIDE from the user's own account (via the idempotent get-or-create, which just
  // returns an existing diary) — never a client-supplied id, so a caller can only erase their OWN
  // diary. The glossary erase deletes by book_id alone, which is why the book_id MUST be the
  // server-resolved one, not a body field.
  @Delete('data')
  async eraseData(@Headers('authorization') authorization?: string): Promise<EraseResult> {
    const { userId, token } = this.requireAuth(authorization);
    const authHeader = `Bearer ${token}`;

    const bookUrl = process.env.BOOK_SERVICE_URL;
    const knowledgeUrl = process.env.KNOWLEDGE_SERVICE_URL;
    const glossaryUrl = process.env.GLOSSARY_SERVICE_URL;
    const chatUrl = process.env.CHAT_SERVICE_URL;
    const internalToken = process.env.INTERNAL_SERVICE_TOKEN;
    if (!bookUrl || !knowledgeUrl || !glossaryUrl || !chatUrl || !internalToken) {
      this.logger.error('assistant-erase rejected: a service URL / INTERNAL_SERVICE_TOKEN not configured');
      throw new HttpException('server_error', 500);
    }

    const uid = encodeURIComponent(userId);
    const deleted: EraseResult['deleted'] = {};
    // Track EVERY attempted leg's success so `erased` means "all data actually gone", not "the book
    // leg happened to succeed" (review MED-2 — a partial failure of the derived legs must NOT report
    // erased:true for an irreversible privacy op).
    let allOk = true;

    // Resolve the user's diary for ANY lifecycle WITHOUT creating one (review MED-1 + LOW-7): the
    // get-or-create endpoint 409s on a TRASHED diary, which made erasing it a silent no-op. This
    // read-only resolver returns the trashed/active/purge_pending diary, or 404 if the user has none.
    const diaryRes = await this.getInternal(`${bookUrl}/internal/books/diary?user_id=${uid}`, internalToken);
    const bookId = diaryRes.ok && typeof diaryRes.body?.book_id === 'string' ? diaryRes.body.book_id : undefined;

    // 1. SOURCE — the assistant chat sessions + messages (the distiller's source). Scope by user_id
    //    ONLY (book_id=None deletes ALL assistant sessions, review MED-5) so a stray session with a
    //    NULL/mismatched book_id can't survive. This is what makes "re-index can't resurrect", so it
    //    runs regardless of whether a diary book was resolved.
    const chat = await this.deleteInternal(`${chatUrl}/internal/chat/assistant/data?user_id=${uid}`, internalToken);
    deleted.chat_sessions = chat.body;
    allOk = allOk && chat.ok;

    let bookErased = false;
    if (bookId) {
      // Resolve the KG project_id BEFORE deleting the book (the get-or-create is keyed on book_id, so
      // resolving it after the book row is gone fails and leaks the project row). Uses the caller's
      // OWN JWT. Done here, up front; the actual KG delete runs in the DERIVED phase below.
      const proj = await this.postJson(`${knowledgeUrl}/v1/knowledge/projects/assistant`, authHeader, { book_id: bookId });
      const projectId = proj.ok && typeof proj.body?.project_id === 'string' ? proj.body.project_id : undefined;

      // 2. SOURCE + OWNERSHIP GATE — the diary book (owner+kind='diary' verified IN the DELETE).
      //    `bookErased` proves the resolved book_id really is THIS user's diary, which is what lets
      //    the un-owner-scoped glossary leg (below) run safely (review MED-4).
      const bookErase = await this.deleteInternal(`${bookUrl}/internal/books/${bookId}/diary/erase?user_id=${uid}`, internalToken);
      deleted.diary_book = bookErase.body;
      bookErased = bookErase.ok && bookErase.body?.erased === true;
      allOk = allOk && bookErase.ok;

      // 3. DERIVED — the KG project + its passages (project_id resolved above, before the book delete).
      if (projectId) {
        const kn = await this.deleteInternal(
          `${knowledgeUrl}/internal/admin/assistant/erase?user_id=${uid}&project_id=${encodeURIComponent(projectId)}`,
          internalToken,
        );
        deleted.knowledge = kn.body;
        allOk = allOk && kn.ok;
      }

      // 4. DERIVED — the captured glossary entities. glossary_entities is book-scoped only (no owner
      //    column), so we ONLY run it once the book erase above has PROVEN this book_id is the
      //    caller's own diary — never trust a book_id the ownership gate didn't confirm (review MED-4).
      if (bookErased) {
        const gl = await this.deleteInternal(`${glossaryUrl}/internal/books/${bookId}/entities`, internalToken);
        deleted.glossary = gl.body;
        allOk = allOk && gl.ok;
      }
    }

    return {
      // erased == every attempted leg succeeded. A user with no diary still gets erased:true once the
      // (only) chat leg succeeds — there was genuinely nothing else. With a diary, ALL legs must pass.
      erased: allOk && (!bookId || bookErased),
      book_id: bookId,
      deleted,
    };
  }

  /** DELETE a token-gated /internal endpoint (D-R27 erasure). Never-throw, report-status contract. */
  private async deleteInternal(
    url: string,
    internalToken: string,
  ): Promise<{ ok: boolean; status: number; body: any }> {
    let resp: globalThis.Response;
    try {
      resp = await fetch(url, {
        method: 'DELETE',
        headers: { 'x-internal-token': internalToken },
        signal: AbortSignal.timeout(PROVISION_STEP_TIMEOUT_MS),
      });
    } catch {
      return { ok: false, status: 0, body: null };
    }
    const text = await resp.text();
    let parsed: any = null;
    try {
      parsed = text ? JSON.parse(text) : null;
    } catch {
      parsed = null;
    }
    return { ok: resp.ok, status: resp.status, body: parsed };
  }

  /**
   * Validate the caller's JWT and return the server-derived identity + the raw token to forward.
   * Identity is NEVER a client body field (SEC-1). Mirrors the book-service/knowledge verifiers:
   * pin HS256, require `exp` (jsonwebtoken has no built-in "require exp") AND a `sub`. Throws
   * 401 (missing/invalid/exp-less) or 500 (JWT_SECRET unconfigured) — the exact contract the
   * provisioning + end-day handlers depend on.
   */
  private requireAuth(authorization?: string): { userId: string; token: string } {
    const token = (authorization ?? '').replace(/^Bearer\s+/i, '').trim();
    if (!token) {
      throw new HttpException('missing bearer token', 401);
    }
    const jwtSecret = process.env.JWT_SECRET;
    if (!jwtSecret) {
      this.logger.error('assistant auth rejected: JWT_SECRET not configured');
      throw new HttpException('server_error', 500);
    }
    let decoded: { exp?: number; sub?: string };
    try {
      decoded = jwt.verify(token, jwtSecret, { algorithms: ['HS256'] }) as { exp?: number; sub?: string };
    } catch {
      throw new HttpException('invalid_token', 401);
    }
    if (typeof decoded.exp !== 'number' || typeof decoded.sub !== 'string' || !decoded.sub) {
      throw new HttpException('invalid_token', 401);
    }
    return { userId: decoded.sub, token };
  }

  /**
   * POST JSON to a token-gated /internal endpoint with the platform INTERNAL_SERVICE_TOKEN
   * (used for system operations like the ontology adopt — NOT a user-authored write, so it
   * carries the service token + a server-derived user_id, never the caller's JWT). Same
   * never-throw, report-status contract as postJson.
   */
  private async postInternal(
    url: string,
    internalToken: string,
    body: unknown,
  ): Promise<{ ok: boolean; status: number; body: any }> {
    let resp: globalThis.Response;
    try {
      resp = await fetch(url, {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'x-internal-token': internalToken },
        body: JSON.stringify(body ?? {}),
        signal: AbortSignal.timeout(PROVISION_STEP_TIMEOUT_MS),
      });
    } catch {
      return { ok: false, status: 0, body: null };
    }
    const text = await resp.text();
    let parsed: any = null;
    try {
      parsed = text ? JSON.parse(text) : null;
    } catch {
      parsed = null;
    }
    return { ok: resp.ok, status: resp.status, body: parsed };
  }

  /** GET a token-gated /internal endpoint (e.g. the auth profile for the display name). Same
   * never-throw, report-status contract as postInternal. */
  private async getInternal(
    url: string,
    internalToken: string,
  ): Promise<{ ok: boolean; status: number; body: any }> {
    let resp: globalThis.Response;
    try {
      resp = await fetch(url, {
        method: 'GET',
        headers: { 'x-internal-token': internalToken },
        signal: AbortSignal.timeout(PROVISION_STEP_TIMEOUT_MS),
      });
    } catch {
      return { ok: false, status: 0, body: null };
    }
    const text = await resp.text();
    let parsed: any = null;
    try {
      parsed = text ? JSON.parse(text) : null;
    } catch {
      parsed = null;
    }
    return { ok: resp.ok, status: resp.status, body: parsed };
  }

  /**
   * POST JSON to a public service endpoint, forwarding the user's Bearer. Never throws on an
   * HTTP or transport error — provisioning treats a failed step as a recorded half-state, not
   * an exception, so one service being down does not abort the whole orchestration. A transport
   * failure is reported as status 0.
   */
  private async postJson(
    url: string,
    authHeader: string,
    body: unknown,
  ): Promise<{ ok: boolean; status: number; body: any }> {
    let resp: globalThis.Response;
    try {
      resp = await fetch(url, {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: authHeader },
        body: JSON.stringify(body ?? {}),
        signal: AbortSignal.timeout(PROVISION_STEP_TIMEOUT_MS),
      });
    } catch {
      return { ok: false, status: 0, body: null };
    }
    const text = await resp.text();
    let parsed: any = null;
    try {
      parsed = text ? JSON.parse(text) : null;
    } catch {
      parsed = null;
    }
    return { ok: resp.ok, status: resp.status, body: parsed };
  }
}
