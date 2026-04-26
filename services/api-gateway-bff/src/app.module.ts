import { Module } from '@nestjs/common';
import { NotificationsModule } from './notifications/notifications.module';
import { WsModule } from './ws/ws.module';

@Module({
  imports: [WsModule, NotificationsModule],
  controllers: [],
  providers: [],
})
export class AppModule {}
