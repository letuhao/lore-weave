import { Controller, Get, Param, Post, Query, Body, Req, UseGuards } from '@nestjs/common';
import { ctxFromReq, glossary, knowledge } from './downstream.js';
import { kgAsOfOrDrop, temporalCapability } from './temporal.js';
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
    return { items: Array.isArray(data?.items) ? data.items : [], temporal_capability: temporalCapability() };
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
    const parsedAsOf = asOf !== undefined ? parseInt(asOf, 10) : undefined;
    const effAsOf = kgAsOfOrDrop(Number.isFinite(parsedAsOf) ? parsedAsOf : undefined);
    if (effAsOf !== undefined) qs.set('as_of_chapter', String(effAsOf));
    const data = (await knowledge.get(
      `/internal/books/${bookId}/kg/neighborhood?${qs.toString()}`,
      ctxFromReq(req),
    )) as Record<string, unknown>;
    return { edges: Array.isArray(data?.edges) ? data.edges : [], temporal_capability: temporalCapability() };
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
    return { items: Array.isArray(data?.items) ? data.items : [], temporal_capability: temporalCapability() };
  }
}
