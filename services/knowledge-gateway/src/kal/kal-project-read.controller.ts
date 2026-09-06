import { Body, Controller, HttpCode, Param, Post, Req, UseGuards } from '@nestjs/common';
import { ctxFromReq, knowledge } from './downstream.js';
import { temporalCapability } from './temporal.js';
import { KalAuthGuard } from '../auth/kal-auth.guard.js';

/** The inbound request shape ctxFromReq needs (identity headers + connection close event). */
type InboundReq = Parameters<typeof ctxFromReq>[0];

/**
 * The PROJECT-scoped half of the KAL read surface (T55/h, spec §8.6 + §8.7).
 *
 * `kal-read.controller.ts` is `v1/kal/books/:bookId` and every read there is book-shaped. Two
 * of the reads §8.6 decided belong behind the KAL are not: their callers hold a project id and
 * no book at all — composition-service works project-shaped, and pushing a book lookup outward
 * would multiply it across 13 services (§8.7 rejected that, and rejected resolving
 * project→book INSIDE the gateway, which is domain logic `gateway-domain-logic-gate` exists to
 * keep out).
 *
 * ⚠️ **This controller exists because a scope AXIS was missing, not a route.** Until
 * `hasProjectAccess` (T55/g) there was no user-mode door here at all: `KalAuthGuard` read
 * `req.params.bookId`, so every JWT request to a project path would have 401'd on
 * `'book scope required'` and left the internal token — which bypasses the guard — as the only
 * way in. A federated read surface whose only usable door is the one that skips authorisation
 * is worse than the direct call it replaces, because it looks governed.
 *
 * The guard is the SAME `KalAuthGuard`, which now dispatches on whichever scope param the
 * route carries. One guard, because the identity half — JWT validation and pinning
 * `req.kalUserId` against header spoofing — is identical and only the authority differs.
 */
@Controller('v1/kal/projects/:projectId')
@UseGuards(KalAuthGuard)
export class KalProjectReadController {
  /**
   * fact-for-check — entities/relations/events as of a story ordinal, for the SCORE guard.
   *
   * §8.6's textbook case: the response carries `valid_from_ordinal` / `valid_to_ordinal` /
   * `event_order` — bi-temporal state on the wire — and it was observed firing in live logs
   * while `knowledge-http-surface-gate` reported PASS, because the gate only knew the reads
   * the KAL already federated.
   */
  @Post('fact-for-check')
  @HttpCode(200)
  async factForCheck(
    @Param('projectId') projectId: string,
    @Body()
    body: {
      entity_ids?: string[];
      glossary_entity_ids?: string[];
      at_order: number;
      relation_limit?: number;
      event_limit?: number;
    },
    @Req() req: InboundReq,
  ) {
    // `projectId` from the PATH, never the body: the path is what the guard scoped, so a
    // body-supplied id would let a caller read one project while authorised for another.
    const data = (await knowledge.post(
      `/internal/projects/${encodeURIComponent(projectId)}/fact-for-check`,
      body,
      ctxFromReq(req),
    )) as Record<string, unknown>;
    return {
      at_order: typeof data?.at_order === 'number' ? data.at_order : body?.at_order,
      entities: Array.isArray(data?.entities) ? data.entities : [],
      relations: Array.isArray(data?.relations) ? data.relations : [],
      events: Array.isArray(data?.events) ? data.events : [],
      temporal_capability: await temporalCapability(ctxFromReq(req)),
    };
  }

  /**
   * glossary-semantic — an entity read reached by semantic search.
   *
   * `entities/search` on the book controller is the same domain question by a different
   * retrieval and is already federated, so §8.6 put this in the same class: consistency, not
   * expansion.
   */
  @Post('glossary-semantic')
  @HttpCode(200)
  async glossarySemantic(
    @Param('projectId') projectId: string,
    @Body() body: { query?: string; max_entities?: number; max_tokens?: number },
    @Req() req: InboundReq,
  ) {
    const ctx = ctxFromReq(req);
    // The owning endpoint takes `user_id` + `project_id` in its BODY. Both come from the
    // request's scope here — the guard's pinned identity and the path — so a caller cannot
    // name a different owner than the one it authenticated as.
    const data = (await knowledge.post(
      `/internal/context/glossary-semantic`,
      { ...body, user_id: ctx.userId, project_id: projectId },
      ctx,
    )) as Record<string, unknown>;
    return {
      items: Array.isArray(data?.items) ? data.items : [],
      temporal_capability: await temporalCapability(ctx),
    };
  }
}
