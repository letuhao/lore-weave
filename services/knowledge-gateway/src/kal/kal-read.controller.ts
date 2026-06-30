import { Controller, Get, Headers, Param, Post, Query, Body, UseGuards } from '@nestjs/common';
import { ctxFromHeaders, glossary, knowledge } from './downstream.js';
import { kgAsOfOrDrop, temporalCapability } from './temporal.js';
import { InternalTokenGuard } from '../auth/internal-token.guard.js';

/**
 * KAL bounded reads (contracts/api/knowledge-gateway/kal.v1.yaml). Every result is bounded;
 * `as_of` is additive and per-substrate gated. The KAL is the only sanctioned caller of the
 * owning services' /internal knowledge routes (INV-KAL).
 *
 * NOTE: downstream path mapping is the live-integration surface. Reads with a stable existing
 * downstream (roster → glossary list_entities) are wired; the rest forward to their documented
 * downstream path and are confirmed by a cross-service live-smoke when the full stack is up.
 */
@UseGuards(InternalTokenGuard)
@Controller('v1/kal/books/:bookId')
export class KalReadController {
  // get_canonical — bounded canonical snapshot (current or as-of N).
  @Get('entities/:entityId/canonical')
  async getCanonical(
    @Param('bookId') bookId: string,
    @Param('entityId') entityId: string,
    @Query('as_of') asOf: string | undefined,
    @Headers() headers: Record<string, string>,
  ) {
    const q = asOf ? `?as_of=${encodeURIComponent(asOf)}` : '';
    const data = await glossary.get(
      `/internal/books/${bookId}/entities/${entityId}/canonical${q}`,
      ctxFromHeaders(headers),
    );
    return data;
  }

  // get_facts — latest-valid (or valid-at-N) facts, per-attribute bounded + temporal capability.
  @Get('entities/:entityId/facts')
  async getFacts(
    @Param('bookId') bookId: string,
    @Param('entityId') entityId: string,
    @Query('as_of') asOf: string | undefined,
    @Query('attrs') attrs: string | undefined,
    @Headers() headers: Record<string, string>,
  ) {
    const qs = new URLSearchParams();
    if (asOf) qs.set('as_of', asOf);
    if (attrs) qs.set('attrs', attrs);
    const data = (await glossary.get(
      `/internal/books/${bookId}/entities/${entityId}/facts?${qs.toString()}`,
      ctxFromHeaders(headers),
    )) as Record<string, unknown>;
    return { items: data?.items ?? data ?? [], temporal_capability: temporalCapability() };
  }

  // timeline — windowed change history (newest-first page).
  @Get('entities/:entityId/timeline')
  async timeline(
    @Param('bookId') bookId: string,
    @Param('entityId') entityId: string,
    @Query() query: Record<string, string>,
    @Headers() headers: Record<string, string>,
  ) {
    const qs = new URLSearchParams(query).toString();
    return glossary.get(`/internal/books/${bookId}/entities/${entityId}/timeline?${qs}`, ctxFromHeaders(headers));
  }

  // list_attr_values — paginated STRUCTURED multi-valued facts (never folded prose, D9).
  @Get('entities/:entityId/attr-values')
  async listAttrValues(
    @Param('bookId') bookId: string,
    @Param('entityId') entityId: string,
    @Query() query: Record<string, string>,
    @Headers() headers: Record<string, string>,
  ) {
    const qs = new URLSearchParams(query).toString();
    return glossary.get(`/internal/books/${bookId}/entities/${entityId}/attr-values?${qs}`, ctxFromHeaders(headers));
  }

  // roster — bounded-per-page, COMPLETE-in-aggregate cast list (§12.5.2 / D4). Keyset cursor;
  // the caller drains next_cursor to completion. Projection-restricted (id+name).
  @Get('roster')
  async roster(
    @Param('bookId') bookId: string,
    @Query('cursor') cursor: string | undefined,
    @Query('limit') limit: string | undefined,
    @Headers() headers: Record<string, string>,
  ) {
    const qs = new URLSearchParams();
    if (cursor) qs.set('cursor', cursor);
    if (limit) qs.set('limit', limit);
    const data = (await glossary.get(
      `/internal/books/${bookId}/entities?${qs.toString()}`,
      ctxFromHeaders(headers),
    )) as Record<string, unknown>;
    const items = ((data?.items as Array<Record<string, unknown>>) ?? []).map((e) => ({
      entity_id: e.entity_id,
      name: e.name ?? e.cached_name,
    }));
    return { items, next_cursor: data?.next_cursor ?? null };
  }

  // search — bounded entity search (top-K).
  @Get('search')
  async search(
    @Param('bookId') bookId: string,
    @Query() query: Record<string, string>,
    @Headers() headers: Record<string, string>,
  ) {
    const qs = new URLSearchParams(query).toString();
    return glossary.get(`/internal/books/${bookId}/entities/search?${qs}`, ctxFromHeaders(headers));
  }

  // neighborhood — KG 1-hop (capped). `as_of` gated per substrate (KG temporal_unsupported pre-F3).
  @Get('entities/:entityId/neighborhood')
  async neighborhood(
    @Param('bookId') bookId: string,
    @Param('entityId') entityId: string,
    @Query('hops') hops: string | undefined,
    @Query('cap') cap: string | undefined,
    @Query('as_of') asOf: string | undefined,
    @Headers() headers: Record<string, string>,
  ) {
    const qs = new URLSearchParams();
    qs.set('entity_id', entityId);
    if (hops) qs.set('hops', hops);
    if (cap) qs.set('cap', cap);
    const effAsOf = kgAsOfOrDrop(asOf ? parseInt(asOf, 10) : undefined);
    if (effAsOf !== undefined) qs.set('as_of_chapter', String(effAsOf));
    const data = (await knowledge.get(
      `/internal/books/${bookId}/kg/neighborhood?${qs.toString()}`,
      ctxFromHeaders(headers),
    )) as Record<string, unknown>;
    return { edges: data?.edges ?? data ?? [], temporal_capability: temporalCapability() };
  }

  // retrieve — semantic top-K over embedded episodes/segments.
  @Post('retrieve')
  async retrieve(
    @Param('bookId') bookId: string,
    @Body() body: { query: string; scope?: string; k?: number; as_of?: number },
    @Headers() headers: Record<string, string>,
  ) {
    const data = await knowledge.post(`/internal/books/${bookId}/retrieve`, body, ctxFromHeaders(headers));
    return { items: (data as Record<string, unknown>)?.items ?? data ?? [], temporal_capability: temporalCapability() };
  }
}
