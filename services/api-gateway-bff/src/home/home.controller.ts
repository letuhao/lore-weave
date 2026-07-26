// M2 (mobile home + activity) — the platform front-door BFF. Two read-composition routes; no new
// truth, no writes to domain data. Mirrors the assistant controller's trust model: validate the
// caller's JWT here, derive identity from `sub` (SEC-1), forward the SAME Bearer to the public
// service APIs so every downstream read is owner-scoped server-side. Gateway invariant (I1): all
// of it lives behind api-gateway-bff; no new public entry point.
//
// GET /v1/home — the degrade contract (spec D-MOB-1 / MB2): the front door must NEVER blank. Fan
// out with Promise.allSettled under a per-source timeout (800ms) and a total wall-clock cap (2s);
// each tile is {status, data|error}. A slow/down source degrades ITS tile only. Sources are
// classified critical (activity unread) vs optional (books/jobs). A short-TTL per-user in-BFF
// cache (45s) lets a flaky downstream serve stale-with-timestamp (up to 5min) rather than blank.
//
// GET /v1/activity — the unified feed over the SINGLE store (notification-service, MB3), keyset
// cursor (no page-boundary dup/drop). POST /v1/activity/mark-all-read — global-per-owner.
import { Controller, Get, Headers, HttpException, Logger, Post, Query } from '@nestjs/common';
import * as jwt from 'jsonwebtoken';

const PER_SOURCE_MS = 800;
const TOTAL_CAP_MS = 2000;
const CACHE_TTL_MS = 45_000; // fresh window
const STALE_MAX_MS = 300_000; // serve last-known up to 5min when a critical source is down
const ACTIVITY_MAX_LIMIT = 50;

type TileStatus = 'ok' | 'empty' | 'degraded';
interface Tile<T> {
  status: TileStatus;
  data?: T;
  error?: string;
}
interface ActivityData {
  unread: number;
}
type BookItem = { id: string; title: string; updated_at?: string };
type JobItem = { id: string; kind?: string; status?: string; created_at?: string };
interface HomeResponse {
  tiles: {
    activity: Tile<ActivityData>;
    books: Tile<BookItem[]>;
    jobs: Tile<JobItem[]>;
  };
  generated_at: string;
  stale?: boolean;
}

interface CursorParts {
  before: string;
  before_id: string;
}

@Controller('v1')
export class HomeController {
  private readonly logger = new Logger(HomeController.name);
  // Per-user in-BFF cache (spec allows Redis OR in-BFF). Per-instance is fine for degrade: each
  // instance serves its own last-known snapshot rather than blanking the page.
  private readonly cache = new Map<string, { at: number; data: HomeResponse }>();
  private static readonly CACHE_MAX_ENTRIES = 5000;

  @Get('home')
  async home(@Headers('authorization') authorization?: string): Promise<HomeResponse> {
    const { userId, token } = this.requireAuth(authorization);
    const authHeader = `Bearer ${token}`;

    const notifUrl = process.env.NOTIFICATION_SERVICE_URL;
    const bookUrl = process.env.BOOK_SERVICE_URL;
    const jobsUrl = process.env.JOBS_SERVICE_URL;

    // Fan out — each source races its own 800ms timeout; the whole batch is additionally capped
    // at 2s (belt-and-suspenders in case a fetch ignores the abort). settle() catches per-source
    // so Promise.all never rejects (it degrades that tile), preserving the typed tuple.
    const settle = <T>(p: Promise<T>): Promise<Tile<T>> =>
      p.then((data) => this.okTile(data)).catch((e) => this.degraded(e));

    const [activity, books, jobs] = await this.raceTotalCap(
      Promise.all([
        settle(this.fetchUnread(notifUrl, authHeader)), // critical
        settle(this.fetchBooks(bookUrl, authHeader)), // optional
        settle(this.fetchJobs(jobsUrl, authHeader)), // optional
      ]),
    );

    const fresh: HomeResponse = {
      tiles: {
        activity: this.emptyIfNoData(activity, (d) => d.unread === 0),
        books: this.emptyIfNoData(books, (d) => d.length === 0),
        jobs: this.emptyIfNoData(jobs, (d) => d.length === 0),
      },
      generated_at: new Date().toISOString(),
    };

    // Cache on a healthy critical source; otherwise serve a recent cached snapshot (never blank).
    if (fresh.tiles.activity.status !== 'degraded') {
      this.evictStale(); // bound the per-user Map so it can't grow forever (cold-review M1)
      this.cache.set(userId, { at: Date.now(), data: fresh });
      return fresh;
    }
    const cached = this.cache.get(userId);
    if (cached && Date.now() - cached.at < STALE_MAX_MS) {
      return { ...cached.data, stale: true, generated_at: cached.data.generated_at };
    }
    return fresh; // no cache to fall back to — return the degraded-but-non-blank page
  }

  @Get('activity')
  async activity(
    @Query('cursor') cursor?: string,
    @Query('limit') limitRaw?: string,
    @Headers('authorization') authorization?: string,
  ): Promise<{ items: unknown[]; next_cursor: string | null; unread_count: number }> {
    const { token } = this.requireAuth(authorization);
    const notifUrl = process.env.NOTIFICATION_SERVICE_URL;
    if (!notifUrl) {
      this.logger.error('activity rejected: NOTIFICATION_SERVICE_URL not configured');
      throw new HttpException('server_error', 500);
    }
    const authHeader = `Bearer ${token}`;

    let limit = parseInt(limitRaw ?? '20', 10);
    if (!Number.isFinite(limit) || limit <= 0) limit = 20;
    if (limit > ACTIVITY_MAX_LIMIT) limit = ACTIVITY_MAX_LIMIT;

    const params = new URLSearchParams({ limit: String(limit) });
    const parts = this.decodeCursor(cursor);
    if (parts) {
      params.set('before', parts.before);
      params.set('before_id', parts.before_id);
    }

    const [list, unread] = await Promise.all([
      this.getJson(`${notifUrl}/v1/notifications?${params.toString()}`, authHeader),
      this.getJson(`${notifUrl}/v1/notifications/unread-count`, authHeader),
    ]);
    if (!list.ok) {
      throw new HttpException('activity_unavailable', 502);
    }
    return {
      items: Array.isArray(list.body?.items) ? list.body.items : [],
      next_cursor: this.encodeCursor(list.body?.next_cursor),
      unread_count: typeof unread.body?.count === 'number' ? unread.body.count : 0,
    };
  }

  @Post('activity/mark-all-read')
  async markAllRead(
    @Headers('authorization') authorization?: string,
  ): Promise<{ marked: number }> {
    const { token } = this.requireAuth(authorization);
    const notifUrl = process.env.NOTIFICATION_SERVICE_URL;
    if (!notifUrl) throw new HttpException('server_error', 500);
    const res = await this.postJson(`${notifUrl}/v1/notifications/read-all`, `Bearer ${token}`, {});
    if (!res.ok) throw new HttpException('mark_all_read_failed', 502);
    return { marked: typeof res.body?.marked === 'number' ? res.body.marked : 0 };
  }

  // ── source fetchers (owner-scoped via the forwarded Bearer) ──────────────

  private async fetchUnread(notifUrl: string | undefined, authHeader: string): Promise<{ unread: number }> {
    if (!notifUrl) throw new Error('notification service not configured');
    const r = await this.getJson(`${notifUrl}/v1/notifications/unread-count`, authHeader);
    if (!r.ok) throw new Error(`unread ${r.status}`);
    return { unread: typeof r.body?.count === 'number' ? r.body.count : 0 };
  }

  private async fetchBooks(bookUrl: string | undefined, authHeader: string): Promise<BookItem[]> {
    if (!bookUrl) throw new Error('book service not configured');
    const r = await this.getJson(`${bookUrl}/v1/books?limit=6`, authHeader);
    if (!r.ok) throw new Error(`books ${r.status}`);
    const items = Array.isArray(r.body?.items) ? r.body.items : [];
    return items.slice(0, 6).map((b: any) => ({ id: String(b.id ?? b.book_id ?? ''), title: String(b.title ?? 'Untitled'), updated_at: b.updated_at }));
  }

  private async fetchJobs(jobsUrl: string | undefined, authHeader: string): Promise<JobItem[]> {
    if (!jobsUrl) throw new Error('jobs service not configured');
    const r = await this.getJson(`${jobsUrl}/v1/jobs?limit=6`, authHeader);
    if (!r.ok) throw new Error(`jobs ${r.status}`);
    const items = Array.isArray(r.body?.items) ? r.body.items : [];
    return items.slice(0, 6).map((j: any) => ({ id: String(j.id ?? j.job_id ?? ''), kind: j.kind ?? j.operation, status: j.status, created_at: j.created_at }));
  }

  // ── tile helpers ─────────────────────────────────────────────────────────

  // Bound the per-user cache: drop entries older than the stale window (they can never be served
  // anyway), and if the Map is still over the size cap, evict oldest-inserted (Map preserves
  // insertion order) until under it. Prevents unbounded growth on a long-running multi-tenant BFF.
  private evictStale(): void {
    const now = Date.now();
    for (const [k, v] of this.cache) {
      if (now - v.at >= STALE_MAX_MS) this.cache.delete(k);
    }
    while (this.cache.size >= HomeController.CACHE_MAX_ENTRIES) {
      const oldest = this.cache.keys().next().value;
      if (oldest === undefined) break;
      this.cache.delete(oldest);
    }
  }

  private okTile<T>(data: T): Tile<T> {
    return { status: 'ok', data };
  }
  private degraded(err: unknown): Tile<never> {
    return { status: 'degraded', error: err instanceof Error ? err.message : 'unavailable' };
  }
  private emptyIfNoData<T>(t: Tile<T>, isEmpty: (d: T) => boolean): Tile<T> {
    if (t.status === 'ok' && t.data !== undefined && isEmpty(t.data)) return { status: 'empty', data: t.data };
    return t;
  }

  // Total wall-clock cap: if the fan-out somehow hasn't settled by 2s (a fetch that ignored its
  // abort), resolve to all-degraded so the page still renders. Typed so the tuple survives.
  private async raceTotalCap<A, B, C>(
    p: Promise<[Tile<A>, Tile<B>, Tile<C>]>,
  ): Promise<[Tile<A>, Tile<B>, Tile<C>]> {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const cap = new Promise<[Tile<A>, Tile<B>, Tile<C>]>((resolve) => {
      timer = setTimeout(
        () => resolve([this.degraded('timeout'), this.degraded('timeout'), this.degraded('timeout')]),
        TOTAL_CAP_MS,
      );
    });
    try {
      return await Promise.race([p, cap]);
    } finally {
      if (timer) clearTimeout(timer); // don't leave the cap timer dangling when the batch wins
    }
  }

  // ── cursor codec (opaque base64 of {before, before_id}) ──────────────────

  private encodeCursor(nc: unknown): string | null {
    if (!nc || typeof nc !== 'object') return null;
    const o = nc as { before?: unknown; before_id?: unknown };
    if (typeof o.before !== 'string' || typeof o.before_id !== 'string') return null;
    return Buffer.from(JSON.stringify({ before: o.before, before_id: o.before_id }), 'utf8').toString('base64url');
  }
  private decodeCursor(cursor?: string): CursorParts | null {
    if (!cursor) return null;
    try {
      const parsed = JSON.parse(Buffer.from(cursor, 'base64url').toString('utf8'));
      if (typeof parsed?.before === 'string' && typeof parsed?.before_id === 'string') {
        return { before: parsed.before, before_id: parsed.before_id };
      }
    } catch {
      /* malformed cursor → treat as first page */
    }
    return null;
  }

  // ── auth + fetch (mirrors assistant.controller: server-derived identity, never-throw fetch) ──

  private requireAuth(authorization?: string): { userId: string; token: string } {
    const token = (authorization ?? '').replace(/^Bearer\s+/i, '').trim();
    if (!token) throw new HttpException('missing bearer token', 401);
    const jwtSecret = process.env.JWT_SECRET;
    if (!jwtSecret) {
      this.logger.error('home auth rejected: JWT_SECRET not configured');
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

  private async getJson(url: string, authHeader: string): Promise<{ ok: boolean; status: number; body: any }> {
    let resp: globalThis.Response;
    try {
      resp = await fetch(url, {
        method: 'GET',
        headers: { authorization: authHeader },
        signal: AbortSignal.timeout(PER_SOURCE_MS),
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

  private async postJson(url: string, authHeader: string, body: unknown): Promise<{ ok: boolean; status: number; body: any }> {
    let resp: globalThis.Response;
    try {
      resp = await fetch(url, {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: authHeader },
        body: JSON.stringify(body ?? {}),
        signal: AbortSignal.timeout(PER_SOURCE_MS),
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
