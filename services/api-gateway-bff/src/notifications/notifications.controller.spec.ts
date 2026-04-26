import { Test } from '@nestjs/testing';
import { firstValueFrom, take, toArray } from 'rxjs';
import * as jwt from 'jsonwebtoken';
import type { Request } from 'express';
import type { EventEmitter } from 'events';

import { AmqpService } from '../ws/amqp.service';
import { NotificationsController } from './notifications.controller';

const TEST_SECRET = 'phase2e-test-secret-32-characters';

class FakeAmqpService {
  private last: ((event: object) => void) | null = null;
  subscribe(_userId: string, handler: (event: object) => void): () => void {
    this.last = handler;
    return () => {
      this.last = null;
    };
  }
  emit(event: object): void {
    this.last?.(event);
  }
}

function makeReq(): Request {
  // Minimal stub matching the controller's req.on('close', ...) usage.
  const handlers: Record<string, Array<() => void>> = {};
  const req = {
    on(event: string, cb: () => void) {
      (handlers[event] ??= []).push(cb);
      return req;
    },
    triggerClose() {
      handlers['close']?.forEach((h) => h());
    },
  } as unknown as Request & { triggerClose: () => void };
  return req;
}

describe('NotificationsController', () => {
  let controller: NotificationsController;
  let amqp: FakeAmqpService;

  beforeEach(async () => {
    process.env.JWT_SECRET = TEST_SECRET;
    amqp = new FakeAmqpService();
    const module = await Test.createTestingModule({
      controllers: [NotificationsController],
      providers: [{ provide: AmqpService, useValue: amqp }],
    }).compile();
    controller = module.get(NotificationsController);
  });

  afterEach(() => {
    delete process.env.JWT_SECRET;
  });

  it('rejects missing token', () => {
    expect(() => controller.stream(undefined, makeReq())).toThrow(
      /missing_token/,
    );
  });

  it('rejects invalid token', () => {
    expect(() => controller.stream('not-a-jwt', makeReq())).toThrow(
      /invalid_token/,
    );
  });

  it('rejects when JWT_SECRET unset', () => {
    delete process.env.JWT_SECRET;
    const validToken = jwt.sign({ sub: 'user-1' }, TEST_SECRET);
    expect(() => controller.stream(validToken, makeReq())).toThrow(
      /server_error/,
    );
  });

  it('forwards events as MessageEvent stream', async () => {
    const token = jwt.sign({ sub: 'user-1' }, TEST_SECRET);
    const req = makeReq();
    const obs = controller.stream(token, req);
    // Take exactly 2 emissions then complete the stream by closing the
    // request — finalize() teardown should unsub from AmqpService.
    const collected = obs.pipe(take(2), toArray());
    setTimeout(() => {
      amqp.emit({ owner_user_id: 'user-1', operation: 'chat', status: 'completed' });
      amqp.emit({ user_id: 'user-1', kind: 'translation.done' });
    }, 0);
    const events = await firstValueFrom(collected);
    expect(events).toHaveLength(2);
    expect((events[0] as { data: object }).data).toEqual({
      owner_user_id: 'user-1',
      operation: 'chat',
      status: 'completed',
    });
    expect((events[1] as { data: object }).data).toEqual({
      user_id: 'user-1',
      kind: 'translation.done',
    });
  });

  it('unsubscribes from AmqpService on req.close', () => {
    const token = jwt.sign({ sub: 'user-2' }, TEST_SECRET);
    const req = makeReq() as Request & { triggerClose: () => void } & EventEmitter;
    const obs = controller.stream(token, req);
    const sub = obs.subscribe();

    // Confirm subscription is active
    let received = 0;
    const inner = obs.subscribe(() => {
      received++;
    });
    amqp.emit({ owner_user_id: 'user-2' });
    expect(received).toBe(1);

    // Trigger close — AmqpService handler should be cleared
    req.triggerClose();
    amqp.emit({ owner_user_id: 'user-2' });
    expect(received).toBe(1); // unchanged

    sub.unsubscribe();
    inner.unsubscribe();
  });
});
