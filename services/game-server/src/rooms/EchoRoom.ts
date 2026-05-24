import { Room, Client, ServerError } from 'colyseus';

// V0 EchoRoom — minimal Colyseus room used by Session E to validate the
// full WebSocket path end-to-end:
//   - auth handshake via onAuth (rejects empty jwt)
//   - bidirectional message via onMessage('echo')
//   - reconnect via Colyseus built-in reconnectionToken
//
// V1+ replaces this with real game rooms (zone instances, combat,
// chat) per spec §17. The pattern of onAuth + onMessage + onDispose
// stays the same; only the message types and state schema grow.

interface JoinOptions {
  jwt?: string;
  userId?: string;
}

interface AuthedUser {
  userId: string;
}

// V0 has no shared state schema — Echo is fire-and-forget messages.
// V1+ Rooms will use Colyseus Schema for state sync.
interface EmptyState {}

export class EchoRoom extends Room<EmptyState, AuthedUser> {
  /**
   * V0 dev token check. Any non-empty jwt that matches the expected
   * env var is accepted. Real JWT verification against auth-service is
   * V1+ scope.
   *
   * Returning the user object makes it available as `client.auth` in
   * onJoin/onLeave/onMessage handlers.
   */
  static expectedToken(): string {
    return process.env.LOREWEAVE_INTERNAL_TOKEN ?? 'dev_token';
  }

  onAuth(_client: Client, options: JoinOptions): AuthedUser {
    const expected = EchoRoom.expectedToken();
    if (!options?.jwt) {
      throw new ServerError(401, 'missing jwt');
    }
    if (options.jwt !== expected) {
      throw new ServerError(403, 'invalid jwt');
    }
    return { userId: options.userId ?? 'guest' };
  }

  onCreate(): void {
    // Reconnect window — clients have 30s after disconnect to call
    // client.reconnect(token) before the server reaps the seat.
    this.setSeatReservationTime(30);

    this.onMessage('echo', (client, message) => {
      client.send('echo', {
        original: message,
        receivedAt: Date.now(),
        echoedBy: 'EchoRoom',
        userId: client.auth.userId,
      });
    });
  }

  onJoin(client: Client): void {
    client.send('welcome', {
      userId: client.auth.userId,
      sessionId: client.sessionId,
      reconnectionToken: client.reconnectionToken,
    });
  }

  async onLeave(client: Client, consented: boolean): Promise<void> {
    if (consented) {
      return;
    }
    // Allow reconnect for the seatReservationTime window.
    try {
      await this.allowReconnection(client, 'manual');
      // If reconnect arrives, control returns here (no further action needed).
    } catch {
      // Reconnect window expired — client truly gone. No-op in V0.
    }
  }
}
