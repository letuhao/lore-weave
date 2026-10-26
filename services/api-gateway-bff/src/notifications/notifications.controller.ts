// Phase 2e (LLM_PIPELINE_UNIFIED_REFACTOR_PLAN). Server-Sent Events
// bridge — FE clients connect to GET /v1/notifications/stream and
// receive any RabbitMQ event published to `loreweave.events` for their
// user_id. Coexists with the WebSocket path /ws which serves the same
// purpose; SSE is preferred by some FE frameworks (and is simpler to
// reconnect/proxy).
//
// Token comes via the `token` query param because browser EventSource
// cannot set an Authorization header. Same convention as the WS path.

import {
  Controller,
  Get,
  HttpException,
  Logger,
  Query,
  Req,
  Sse,
  UnauthorizedException,
} from '@nestjs/common';
import { Observable, Subject } from 'rxjs';
import { finalize } from 'rxjs/operators';
import * as jwtModule from 'jsonwebtoken';
// CRITICAL interop fix (2026-10-24): under node's ESM the namespace import of
// this CJS `export =` package has NO named members (the lexer cannot see
// through `module.exports = { decode: require('./decode'), ... }`), so
// `jwt.verify` would be undefined at runtime. The default binding IS
// module.exports in both node and jest — resolve to it explicitly.
const jwt = ((jwtModule as { default?: unknown }).default ?? jwtModule) as typeof import('jsonwebtoken');

import type { Request } from 'express';

import { AmqpService } from '../ws/amqp.service.js';

interface NotificationMessageEvent {
  data: object;
  type?: string;
  id?: string;
}

@Controller('v1/notifications')
export class NotificationsController {
  private readonly logger = new Logger(NotificationsController.name);

  constructor(private readonly amqp: AmqpService) {}

  /**
   * SSE endpoint. Subscribes the connected client to its user's
   * RabbitMQ event stream via AmqpService and forwards each event as
   * an SSE message. The Subject is completed (and the AMQP handler
   * unsubscribed) when the client disconnects, via the RxJS finalize
   * operator.
   */
  @Sse('stream')
  stream(
    @Query('token') token: string | undefined,
    @Req() req: Request,
  ): Observable<NotificationMessageEvent> {
    if (!token) {
      this.logger.warn('SSE rejected: missing_token');
      // Auth failures MUST be HttpExceptions: a bare Error maps to a 500. The
      // throws happen before the Observable is built, so no SSE headers have
      // been sent and Nest answers with a clean JSON status (measured 500→401,
      // 2026-10-25).
      throw new UnauthorizedException('missing_token');
    }
    const jwtSecret = process.env.JWT_SECRET;
    if (!jwtSecret) {
      this.logger.error('SSE rejected: JWT_SECRET not configured');
      throw new HttpException('server_error', 500);
    }

    let userId: string;
    try {
      // P3 (security): pin the HS256 allow-list so a token can't dictate its own
      // verify algorithm (alg-confusion / alg:none defense), matching
      // tools.controller + the platform verifier posture.
      const decoded = jwt.verify(token, jwtSecret, { algorithms: ['HS256'] }) as { sub: string };
      userId = decoded.sub;
    } catch (err) {
      this.logger.warn(
        `SSE rejected: invalid_token — ${(err as Error).message}`,
      );
      throw new UnauthorizedException('invalid_token');
    }

    const subject = new Subject<NotificationMessageEvent>();
    const unsubscribe = this.amqp.subscribe(userId, (event) => {
      subject.next({ data: event });
    });

    this.logger.log(`SSE connected: user ${userId}`);

    // Detect client-side close so we drop the AmqpService handler. NestJS
    // calls the Observable's teardown when the underlying response ends;
    // we use finalize() to clean up.
    req.on('close', () => {
      unsubscribe();
      subject.complete();
      this.logger.log(`SSE disconnected: user ${userId}`);
    });

    return subject.asObservable().pipe(
      finalize(() => {
        unsubscribe();
      }),
    );
  }
}
