import {
  WebSocketGateway,
  WebSocketServer,
  OnGatewayConnection,
  OnGatewayDisconnect,
} from '@nestjs/websockets';
import { Logger } from '@nestjs/common';
import { Server } from 'ws';
import type { WebSocket } from 'ws';
import type { IncomingMessage } from 'http';
import * as jwt from 'jsonwebtoken';
import { AmqpService } from './amqp.service';

@WebSocketGateway({ path: '/ws' })
export class EventsGateway implements OnGatewayConnection, OnGatewayDisconnect {
  @WebSocketServer()
  server!: Server;

  private readonly logger = new Logger(EventsGateway.name);
  private readonly unsubs = new Map<WebSocket, () => void>();

  constructor(private readonly amqp: AmqpService) {}

  handleConnection(socket: WebSocket, req: IncomingMessage): void {
    const rawUrl = req.url ?? '';
    let token: string | null = null;
    try {
      token = new URL(rawUrl, 'http://x').searchParams.get('token');
    } catch {
      socket.close(4001, 'invalid_url');
      return;
    }

    if (!token) {
      this.logger.warn('WS rejected: missing_token');
      socket.close(4001, 'missing_token');
      return;
    }

    const jwtSecret = process.env.JWT_SECRET;
    if (!jwtSecret) {
      this.logger.error('WS rejected: JWT_SECRET not configured');
      socket.close(4500, 'server_error');
      return;
    }

    let userId: string;
    try {
      const decoded = jwt.verify(token, jwtSecret) as { sub: string };
      userId = decoded.sub;
    } catch (err) {
      this.logger.warn(`WS rejected: invalid_token — ${(err as Error).message}`);
      socket.close(4001, 'invalid_token');
      return;
    }

    const unsub = this.amqp.subscribe(userId, (event) => {
      if (socket.readyState === socket.OPEN) {
        socket.send(JSON.stringify(event));
      }
    });

    this.unsubs.set(socket, unsub);
    this.logger.log(`WS connected: user ${userId} (total=${this.unsubs.size})`);
  }

  handleDisconnect(socket: WebSocket): void {
    const unsub = this.unsubs.get(socket);
    if (unsub) {
      unsub();
      this.unsubs.delete(socket);
      this.logger.log(`WS disconnected (total=${this.unsubs.size})`);
    }
  }
}
