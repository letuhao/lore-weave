import { Module } from '@nestjs/common';
import { AssistantModule } from './assistant/assistant.module';
import { HomeModule } from './home/home.module';
import { NotificationsModule } from './notifications/notifications.module';
import { ToolsModule } from './tools/tools.module';
import { WsModule } from './ws/ws.module';

@Module({
  imports: [WsModule, NotificationsModule, ToolsModule, AssistantModule, HomeModule],
  controllers: [],
  providers: [],
})
export class AppModule {}
