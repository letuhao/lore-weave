import { Controller, Get, Param, Post, Query, Body, Req, UseGuards } from '@nestjs/common';
import { ctxFromReq, glossary, knowledge } from './downstream.js';
import { temporalCapability } from './temporal.js';
import { KalAuthGuard } from '../auth/kal-auth.guard.js';

/** The inbound request shape ctxFromReq needs (identity headers + connection close event). */
type InboundReq = Parameters<typeof ctxFromReq>[0];

/**
 * KAL bounded reads (contracts/api/knowledge-gateway/kal.v1.yaml). Every result is bounded;
 * `as_of` is additive and per-substrate gated. The KAL is the only sanctioned caller of the
 * owning services' /internal knowledge routes (INV-KAL).
 *
 * NOTE: downstream path mapping is the live-integration surface. Reads with a stable existing
 * downstream (roster → glossary list_entities) are wired; the rest forward to their documented
 * downstream path and are confirmed by a cross-service live-smoke when the full stack is up.
 */
@UseGuards(KalAuthGuard)
@Controller('v1/kal/books/:bookId')
export class KalReadController {
  // get_canonical — bounded canonical snapshot (current or as-of N).
  @Get('entities/:entityId/canonical')
  async getCanonical(
    @Param('bookId') bookId: string,
    @Param('entityId') entityId: string,
    @Query('as_of') asOf: string | undefined,
    @Req() req: InboundReq,
  ) {
    // The folded canonical snapshot (F2-app), degrade-safe to canon-content when no fresh
    // snapshot exists. `as_of` below the fold head projects from facts (get_facts) — the
    // snapshot is the head cache.
    const q = asOf ? `?as_of=${encodeURIComponent(asOf)}` : '';
    const data = await glossary.get(
      `/internal/books/${bookId}/entities/${entityId}/canonical-snapshot${q}`,
      ctxFromReq(req),
    );
    return data;
  }

  // get_canonical_translation — the as-of folded canonical translated into `lang`, on-demand +
  // cached immutable per (content, language) (§6B/§7.6). Read-through: status `translating` while
  // the single-flight background fill runs (the FE polls); `ready` carries the translated content;
  // `failed`/`unbuildable` degrade. The LLM runs in translation-service (BYOK, provider-registry).
  @Get('entities/:entityId/canonical-translation')
  async getCanonicalTranslation(
    @Param('bookId') bookId: string,
    @Param('entityId') entityId: string,
    @Query('lang') lang: string | undefined,
    @Query('as_of') asOf: string | undefined,
    @Req() req: InboundReq,
  ) {
    const qs = new URLSearchParams();
    if (lang) qs.set('lang', lang);
    if (asOf) qs.set('as_of', asOf);
    return glossary.get(
      `/internal/books/${bookId}/entities/${entityId}/canonical-translation?${qs.toString()}`,
      ctxFromReq(req),
    );
  }

  // get_facts — latest-valid (or valid-at-N) facts, per-attribute bounded + temporal capability.
  @Get('entities/:entityId/facts')
  async getFacts(
    @Param('bookId') bookId: string,
    @Param('entityId') entityId: string,
    @Query('as_of') asOf: string | undefined,
    @Query('attrs') attrs: string | undefined,
    @Req() req: InboundReq,
  ) {
    const qs = new URLSearchParams();
    if (asOf) qs.set('as_of', asOf);
    if (attrs) qs.set('attrs', attrs);
    const data = (await glossary.get(
      `/internal/books/${bookId}/entities/${entityId}/facts?${qs.toString()}`,
      ctxFromReq(req),
    )) as Record<string, unknown>;
    // Strict array coercion: a downstream object that lacks `items` must NOT pass through
    // whole as the bounded item array (the contract types items as array<Fact>). Never `?? data`.
    return { items: Array.isArray(data?.items) ? data.items : [], temporal_capability: await temporalCapability(ctxFromReq(req)) };
  }

  // timeline — windowed change history (newest-first page).
  @Get('entities/:entityId/timeline')
  async timeline(
    @Param('bookId') bookId: string,
    @Param('entityId') entityId: string,
    @Query() query: Record<string, string>,
    @Req() req: InboundReq,
  ) {
    const qs = new URLSearchParams(query).toString();
    return glossary.get(`/internal/books/${bookId}/entities/${entityId}/timeline?${qs}`, ctxFromReq(req));
  }

  // list_attr_values — paginated STRUCTURED multi-valued facts (never folded prose, D9).
  @Get('entities/:entityId/attr-values')
  async listAttrValues(
    @Param('bookId') bookId: string,
    @Param('entityId') entityId: string,
    @Query() query: Record<string, string>,
    @Req() req: InboundReq,
  ) {
    const qs = new URLSearchParams(query).toString();
    return glossary.get(`/internal/books/${bookId}/entities/${entityId}/attr-values?${qs}`, ctxFromReq(req));
  }

  // roster — bounded-per-page, COMPLETE-in-aggregate cast list (§12.5.2 / D4). Keyset cursor;
  // the caller drains next_cursor to completion. Projection-restricted (id+name).
  @Get('roster')
  async roster(
    @Param('bookId') bookId: string,
    @Query('cursor') cursor: string | undefined,
    @Query('limit') limit: string | undefined,
    @Req() req: InboundReq,
  ) {
    const qs = new URLSearchParams();
    if (cursor) qs.set('cursor', cursor);
    if (limit) qs.set('limit', limit);
    const data = (await glossary.get(
      `/internal/books/${bookId}/entities?${qs.toString()}`,
      ctxFromReq(req),
    )) as Record<string, unknown>;
    const items = ((data?.items as Array<Record<string, unknown>>) ?? []).map((e) => ({
      entity_id: e.entity_id,
      name: e.name ?? e.cached_name,
      // A3 — pass the entity's KIND through (the upstream already selects k.code AS kind_code). Lets
      // consumers (the PlanForge gather lens) rank/label cast by importance — protagonist first —
      // instead of by drain order. One short scalar; the projection stays bounded.
      kind: e.kind_code ?? e.kind ?? null,
    }));
    return { items, next_cursor: data?.next_cursor ?? null };
  }

  // cast — the DETAIL read (T38 B1/B2). `roster` answers "who is in this book" with
  // id+name+kind; every one of T38's ten pinned consumers needs more than that, which is why
  // 0 of 10 could migrate onto `roster` and four of them went straight to the glossary's
  // `entities/by-ids` instead. This is the missing rung.
  //
  // ── WHY IT SITS BESIDE `roster` AND `by-ids` RATHER THAN REPLACING EITHER ────────────────
  // `roster` is DELIBERATELY projection-restricted and drains a whole book; widening it would
  // put aliases and descriptions on the enumeration path every indexing pass walks. And
  // `entities/by-ids` is a POST keyed by an id LIST — a different question ("these specific
  // entities"), not a page of a book. `cast` is the page-shaped detail read: same keyset
  // cursor as `roster`, richer projection, one book.
  //
  // ── THE HONEST CAP ──────────────────────────────────────────────────────────────────────
  // `truncated` is returned EXPLICITLY rather than left to be inferred from a short page. A
  // caller that stops when `items.length < limit` is guessing, and the guess is wrong exactly
  // when the upstream capped it — the silent-truncation shape that once cut a deep book's cast
  // at ~100 and reported a complete-looking count.
  @Get('cast')
  async cast(
    @Param('bookId') bookId: string,
    @Query('cursor') cursor: string | undefined,
    @Query('limit') limit: string | undefined,
    @Req() req: InboundReq,
  ) {
    const qs = new URLSearchParams();
    if (cursor) qs.set('cursor', cursor);
    if (limit) qs.set('limit', limit);
    const data = (await glossary.get(
      `/internal/books/${bookId}/entities?${qs.toString()}`,
      ctxFromReq(req),
    )) as Record<string, unknown>;
    const raw = (data?.items as Array<Record<string, unknown>>) ?? [];
    const items = raw.map((e) => ({
      entity_id: e.entity_id,
      // `name` keeps `roster`'s meaning so a consumer can move between the two reads without
      // relearning the field; `cached_name` is carried as well because two of the pinned
      // consumers ask for it BY THAT NAME and silently dropping it would look like a null.
      name: e.name ?? e.cached_name ?? null,
      cached_name: e.cached_name ?? e.name ?? null,
      kind: e.kind_code ?? e.kind ?? null,
      aliases: Array.isArray(e.cached_aliases) ? e.cached_aliases : [],
      short_description: e.short_description ?? null,
    }));
    return {
      items,
      next_cursor: data?.next_cursor ?? null,
      // Explicit, never inferred. See the cap note above.
      truncated: data?.next_cursor != null,
    };
  }

  // state — the book-wide as-of read (AC1/AC2). One value per (entity, attribute) at story
  // position N, across the whole cast.
  //
  // `as_of` is REQUIRED and the gateway does NOT enforce that itself. It forwards whatever
  // arrived and glossary answers 400 (downstream 4xx is propagated faithfully by
  // `downstream.ts`). Deliberate: a second copy of the rule in TypeScript is a rule that can
  // drift out of agreement with the one that owns it, and decision B2 says the gateway carries
  // no domain logic. Forwarding an empty `as_of` reaches the same refusal as omitting it —
  // glossary treats both as "no story position".
  //
  // Unlike `roster`, this read is NOT projection-restricted to id+name: its whole purpose is to
  // answer what was TRUE at a position, and a name-only projection cannot. It stays bounded by
  // the position instead — only intervals covering N, one per attribute.
  @Get('state')
  async state(
    @Param('bookId') bookId: string,
    @Query('as_of') asOf: string | undefined,
    @Req() req: InboundReq,
  ) {
    const qs = new URLSearchParams();
    if (asOf !== undefined) qs.set('as_of', asOf);
    const data = (await glossary.get(
      `/internal/books/${bookId}/state?${qs.toString()}`,
      ctxFromReq(req),
    )) as Record<string, unknown>;
    // Strict array coercion, same as get_facts: a downstream object without `entities` must not
    // pass through whole as the bounded list. Never `?? data`.
    return {
      book_id: data?.book_id ?? bookId,
      as_of_ordinal: data?.as_of_ordinal ?? null,
      entities: Array.isArray(data?.entities) ? data.entities : [],
      temporal_capability: await temporalCapability(ctxFromReq(req)),
    };
  }

  // search — bounded entity search (top-K).
  @Get('search')
  async search(
    @Param('bookId') bookId: string,
    @Query() query: Record<string, string>,
    @Req() req: InboundReq,
  ) {
    const qs = new URLSearchParams(query).toString();
    return glossary.get(`/internal/books/${bookId}/entities/search?${qs}`, ctxFromReq(req));
  }

  // neighborhood — KG 1-hop (capped). `as_of` gated per substrate (KG temporal_unsupported pre-F3).
  @Get('entities/:entityId/neighborhood')
  async neighborhood(
    @Param('bookId') bookId: string,
    @Param('entityId') entityId: string,
    @Query('hops') hops: string | undefined,
    @Query('cap') cap: string | undefined,
    @Query('as_of') asOf: string | undefined,
    @Req() req: InboundReq,
  ) {
    const qs = new URLSearchParams();
    qs.set('entity_id', entityId);
    if (hops) qs.set('hops', hops);
    if (cap) qs.set('cap', cap);
    // Guard parseInt: a non-numeric as_of must not forward literal "NaN" downstream — drop it.
    // That is a PARSING guard, not a domain one. Whether the KG can honour a well-formed
    // as_of is the owning service's call (T26); the gateway used to decide it from its own
    // env var and could disagree with the substrate it was describing.
    const parsedAsOf = asOf !== undefined ? parseInt(asOf, 10) : undefined;
    if (parsedAsOf !== undefined && Number.isFinite(parsedAsOf)) {
      qs.set('as_of_chapter', String(parsedAsOf));
    }
    const data = (await knowledge.get(
      `/internal/books/${bookId}/kg/neighborhood?${qs.toString()}`,
      ctxFromReq(req),
    )) as Record<string, unknown>;
    return { edges: Array.isArray(data?.edges) ? data.edges : [], temporal_capability: await temporalCapability(ctxFromReq(req)) };
  }

  // retrieve — semantic top-K over embedded episodes/segments.
  @Post('retrieve')
  async retrieve(
    @Param('bookId') bookId: string,
    @Body() body: { query: string; scope?: string; k?: number; as_of?: number },
    @Req() req: InboundReq,
  ) {
    const data = (await knowledge.post(
      `/internal/books/${bookId}/retrieve`,
      body,
      ctxFromReq(req),
    )) as Record<string, unknown>;
    return { items: Array.isArray(data?.items) ? data.items : [], temporal_capability: await temporalCapability(ctxFromReq(req)) };
  }
}
