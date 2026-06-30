import { Body, Controller, Param, Post, UseGuards } from '@nestjs/common';
import { ctxFromHeaders, glossary } from './downstream.js';
import { Headers } from '@nestjs/common';
import { InternalTokenGuard } from '../auth/internal-token.guard.js';

/**
 * KAL writes (the only mutators) — encode the two write paths (A append / B retract) +
 * close/merge/split/resolve/episode/fold (§4, §12.4). Each delegates to a glossary-service
 * `/internal/*` route that wraps the Go fact core (ingestEpisode / appendFact / closeFact /
 * retractFacts / mergeFactChains / splitFactsByEpisode / resolveEntity / triggerFold). ALL of
 * these routes are backed (F4 + close_fact); the KAL forwards and surfaces the downstream status
 * faithfully (a 4xx is the caller's to see), never a silent success. The WRITE surface is
 * internal-token-only — the FE never writes facts directly (those are the producer/service path).
 */
@UseGuards(InternalTokenGuard)
@Controller('v1/kal/books/:bookId')
export class KalWriteController {
  @Post('episodes')
  ingestEpisode(@Param('bookId') bookId: string, @Body() body: unknown, @Headers() h: Record<string, string>) {
    return this.forward(bookId, 'episode', body, h);
  }

  @Post('resolve-entity')
  resolveEntity(@Param('bookId') bookId: string, @Body() body: unknown, @Headers() h: Record<string, string>) {
    return this.forward(bookId, 'resolve-entity', body, h);
  }

  @Post('facts')
  appendFact(@Param('bookId') bookId: string, @Body() body: unknown, @Headers() h: Record<string, string>) {
    return this.forward(bookId, 'append', body, h);
  }

  @Post('facts/close')
  closeFact(@Param('bookId') bookId: string, @Body() body: unknown, @Headers() h: Record<string, string>) {
    // → /internal/books/{id}/facts/close (internalCloseFact). Explicit valid-time close (§12.3.2):
    // glossary pins the fact's valid_to via the pin-aware maintain_chain (migration 0049) so the
    // close survives chain re-derivation — the LOCKED single-writer invariant holds (a pinned close
    // is an authored INPUT the deriver respects, not a competing writer). Backed + live-smoked.
    return this.forward(bookId, 'close', body, h);
  }

  @Post('retract')
  retract(@Param('bookId') bookId: string, @Body() body: unknown, @Headers() h: Record<string, string>) {
    return this.forward(bookId, 'retract', body, h);
  }

  @Post('entities/merge')
  merge(@Param('bookId') bookId: string, @Body() body: unknown, @Headers() h: Record<string, string>) {
    return this.forward(bookId, 'merge', body, h);
  }

  @Post('entities/split')
  split(@Param('bookId') bookId: string, @Body() body: unknown, @Headers() h: Record<string, string>) {
    return this.forward(bookId, 'split', body, h);
  }

  @Post('entities/:entityId/fold')
  fold(
    @Param('bookId') bookId: string,
    @Param('entityId') entityId: string,
    @Body() body: unknown,
    @Headers() h: Record<string, string>,
  ) {
    // Fold is NOT a facts/* verb — it lives at the entity, not the fact chain. Marks the entity's
    // canonical dirty so the next fold pass (translation worker, via provider-registry) folds it.
    return glossary.post(
      `/internal/books/${bookId}/entities/${entityId}/fold`,
      body ?? {},
      ctxFromHeaders(h),
    );
  }

  /** Forward to the glossary fact-core internal route under /facts/. downstream.ts maps a 4xx
   *  through faithfully (the caller's to see) and 5xx → 502 — never a silent success. */
  private async forward(bookId: string, verb: string, body: unknown, h: Record<string, string>) {
    return glossary.post(`/internal/books/${bookId}/facts/${verb}`, body, ctxFromHeaders(h));
  }
}
