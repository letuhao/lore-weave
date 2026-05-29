import { Module } from '@nestjs/common';
import { AmqpService } from './amqp.service';
import { EventsGateway } from './events.gateway';
import { WsV1Gateway } from './ws-server';
import { TicketController, TICKET_STORE_TOKEN } from './ticket-endpoint';
import { InMemoryTicketStore, type TicketStore } from './ticket-store';
import { InMemoryAuthzProvider, type SessionAuthzProvider } from './per-message-authz';

/**
 * Foundation-grade WS server wiring.
 *
 * Cycle 28 (L6.A + L6.B + L6.E) adds:
 *   - `WsV1Gateway` at /ws/v1 (ticket-handshake server)
 *   - `TicketController` at POST /v1/ws/ticket
 *   - Shared TicketStore (in-memory V1; Redis swap-in in L7 deploy track)
 *
 * Cycle 29 (L6.C + L6.D) adds:
 *   - `PerMessageAuthz` wired into WsV1Gateway via 'AUTHZ_PROVIDER' token
 *     (foundation uses InMemoryAuthzProvider; downstream service swaps in
 *     a roleplay-service RPC client)
 *   - Forced-disconnect Redis pubsub consumer (wired by deploy code at
 *     boot — kept out of the module here because Redis isn't required
 *     for unit tests to pass)
 *
 * The legacy `EventsGateway` (/ws, JWT-on-query) stays online for
 * parallel rollout — frontend-game flips clients to /ws/v1 once the
 * browser ticket lib (their domain, per Q-L6-3) is ready.
 */
const sharedTicketStore: TicketStore = new InMemoryTicketStore();
const sharedAuthzProvider: SessionAuthzProvider = new InMemoryAuthzProvider();

@Module({
  providers: [
    AmqpService,
    EventsGateway,
    WsV1Gateway,
    {
      provide: TICKET_STORE_TOKEN,
      useValue: sharedTicketStore,
    },
    {
      provide: 'AUTHZ_PROVIDER',
      useValue: sharedAuthzProvider,
    },
  ],
  controllers: [TicketController],
  exports: [AmqpService],
})
export class WsModule {}
