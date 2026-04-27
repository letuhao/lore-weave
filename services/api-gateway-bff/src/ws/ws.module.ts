import { Module } from '@nestjs/common';
import { AmqpService } from './amqp.service';
import { EventsGateway } from './events.gateway';

@Module({
  providers: [AmqpService, EventsGateway],
  exports: [AmqpService],
})
export class WsModule {}
