import { Module } from '@nestjs/common';
import { AssistantModule } from './assistant/assistant.module.js';
import { HomeModule } from './home/home.module.js';
import { NotificationsModule } from './notifications/notifications.module.js';
import { ToolsModule } from './tools/tools.module.js';
import { WsModule } from './ws/ws.module.js';

@Module({
  imports: [WsModule, NotificationsModule, ToolsModule, AssistantModule, HomeModule],
  controllers: [],
  providers: [],
})
export class AppModule {}
