import { Module } from '@nestjs/common';
import { NotificationsModule } from './notifications/notifications.module';
import { ToolsModule } from './tools/tools.module';
import { WsModule } from './ws/ws.module';

@Module({
  imports: [WsModule, NotificationsModule, ToolsModule],
  controllers: [],
  providers: [],
})
export class AppModule {}
