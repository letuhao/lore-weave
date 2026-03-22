import { Module } from '@nestjs/common';
import { AmqpService } from './amqp.service';
import { EventsGateway } from './events.gateway';

@Module({
  providers: [AmqpService, EventsGateway],
})
export class WsModule {}
