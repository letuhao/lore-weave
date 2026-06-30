import { Body, Controller, Param, Post, UseGuards } from '@nestjs/common';
import { ctxFromHeaders, glossary } from './downstream.js';
import { Headers } from '@nestjs/common';
import { InternalTokenGuard } from '../auth/internal-token.guard.js';

/**
 * KAL writes (the only mutators) — encode the two write paths (A append / B retract) +
 * merge/split + fold (§4, §12.4). Each delegates to a glossary-service `/internal/facts/*`
 * route that wraps the Go fact core (appendFact / retractFacts / mergeFactChains /
 * splitFactsByEpisode / fold). Those internal routes are the F4-follow-on (the fact core
 * exists as Go functions today, F1c/F1f); until a route is exposed the KAL forwards and
 * surfaces the downstream status (a 404 "route not yet exposed"), never a silent success.
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
    return this.forward(bookId, 'facts/close', body, h);
  }

  @Post('retract')
  retract(@Param('bookId') bookId: string, @Body() body: unknown, @Headers() h: Record<string, string>) {
    return this.forward(bookId, 'retract', body, h);
  }

  @Post('entities/merge')
  merge(@Param('bookId') bookId: string, @Body() body: unknown, @Headers() h: Record<string, string>) {
    return this.forward(bookId, 'entities/merge', body, h);
  }

  @Post('entities/split')
  split(@Param('bookId') bookId: string, @Body() body: unknown, @Headers() h: Record<string, string>) {
    return this.forward(bookId, 'entities/split', body, h);
  }

  @Post('entities/:entityId/fold')
  fold(
    @Param('bookId') bookId: string,
    @Param('entityId') entityId: string,
    @Body() body: unknown,
    @Headers() h: Record<string, string>,
  ) {
    return this.forward(bookId, `entities/${entityId}/fold`, body, h);
  }

  /** Forward to the glossary fact-core internal route; 502→501 surfaces "route not yet exposed". */
  private async forward(bookId: string, verb: string, body: unknown, h: Record<string, string>) {
    return glossary.post(`/internal/books/${bookId}/facts/${verb}`, body, ctxFromHeaders(h));
  }
}
