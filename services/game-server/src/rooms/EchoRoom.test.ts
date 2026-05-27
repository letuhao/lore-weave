import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { authenticate, expectedToken } from './EchoRoom.js';
import { ServerError } from 'colyseus';

describe('EchoRoom.authenticate', () => {
  const TOKEN = 'test-token-xyz';

  it('returns user with default userId guest when jwt matches and userId absent', () => {
    const u = authenticate({ jwt: TOKEN }, TOKEN);
    assert.equal(u.userId, 'guest');
  });

  it('returns user with provided userId', () => {
    const u = authenticate({ jwt: TOKEN, userId: 'alice' }, TOKEN);
    assert.equal(u.userId, 'alice');
  });

  it('throws 401 ServerError when jwt is missing', () => {
    assert.throws(
      () => authenticate({}, TOKEN),
      (err) => err instanceof ServerError && err.code === 401,
    );
  });

  it('throws 401 when options is undefined', () => {
    assert.throws(
      () => authenticate(undefined, TOKEN),
      (err) => err instanceof ServerError && err.code === 401,
    );
  });

  it('throws 401 when jwt is empty string', () => {
    assert.throws(
      () => authenticate({ jwt: '' }, TOKEN),
      (err) => err instanceof ServerError && err.code === 401,
    );
  });

  it('throws 403 ServerError when jwt does not match expected', () => {
    assert.throws(
      () => authenticate({ jwt: 'wrong-token' }, TOKEN),
      (err) => err instanceof ServerError && err.code === 403,
    );
  });
});

describe('EchoRoom.expectedToken', () => {
  it('returns env LOREWEAVE_INTERNAL_TOKEN when set', () => {
    const original = process.env.LOREWEAVE_INTERNAL_TOKEN;
    process.env.LOREWEAVE_INTERNAL_TOKEN = 'env-set-token';
    try {
      assert.equal(expectedToken(), 'env-set-token');
    } finally {
      if (original === undefined) {
        delete process.env.LOREWEAVE_INTERNAL_TOKEN;
      } else {
        process.env.LOREWEAVE_INTERNAL_TOKEN = original;
      }
    }
  });

  it('falls back to "dev_token" when env is unset', () => {
    const original = process.env.LOREWEAVE_INTERNAL_TOKEN;
    delete process.env.LOREWEAVE_INTERNAL_TOKEN;
    try {
      assert.equal(expectedToken(), 'dev_token');
    } finally {
      if (original !== undefined) {
        process.env.LOREWEAVE_INTERNAL_TOKEN = original;
      }
    }
  });
});
