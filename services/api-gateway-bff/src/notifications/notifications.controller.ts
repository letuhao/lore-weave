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
  Logger,
  Query,
  Req,
  Sse,
} from '@nestjs/common';
import { Observable, Subject } from 'rxjs';
import { finalize } from 'rxjs/operators';
import * as jwt from 'jsonwebtoken';
import type { Request } from 'express';

import { AmqpService } from '../ws/amqp.service';

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
      throw new Error('missing_token');
    }
    const jwtSecret = process.env.JWT_SECRET;
    if (!jwtSecret) {
      this.logger.error('SSE rejected: JWT_SECRET not configured');
      throw new Error('server_error');
    }

    let userId: string;
    try {
      const decoded = jwt.verify(token, jwtSecret) as { sub: string };
      userId = decoded.sub;
    } catch (err) {
      this.logger.warn(
        `SSE rejected: invalid_token — ${(err as Error).message}`,
      );
      throw new Error('invalid_token');
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
