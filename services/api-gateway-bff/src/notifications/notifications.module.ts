// Phase 2e — module wires the NotificationsController to the existing
// AmqpService instance from WsModule. Coexists with /ws (WebSocket).

import { Module } from '@nestjs/common';
import { WsModule } from '../ws/ws.module.js';
import { NotificationsController } from './notifications.controller.js';

@Module({
  imports: [WsModule],
  controllers: [NotificationsController],
})
export class NotificationsModule {}
