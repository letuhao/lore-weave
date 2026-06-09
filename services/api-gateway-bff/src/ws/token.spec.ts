import * as jwt from 'jsonwebtoken';
import { resolveUserIdFromToken, requireStreamTicketEnforced } from './token';

const secret = 'test-jwt-secret-at-least-32-characters-long';

describe('resolveUserIdFromToken', () => {
  const prev = process.env.BFF_REQUIRE_STREAM_TICKET;

  afterEach(() => {
    if (prev === undefined) {
      delete process.env.BFF_REQUIRE_STREAM_TICKET;
    } else {
      process.env.BFF_REQUIRE_STREAM_TICKET = prev;
    }
  });

  it('accepts stream ticket when enforcement on', () => {
    process.env.BFF_REQUIRE_STREAM_TICKET = 'true';
    const token = jwt.sign({ typ: 'stream', sub: 'user-1' }, secret, { expiresIn: '2m' });
    expect(resolveUserIdFromToken(token, secret)).toBe('user-1');
    expect(requireStreamTicketEnforced()).toBe(true);
  });

  it('rejects access JWT when enforcement on', () => {
    process.env.BFF_REQUIRE_STREAM_TICKET = 'true';
    const token = jwt.sign({ sub: 'user-1' }, secret, { expiresIn: '15m' });
    expect(() => resolveUserIdFromToken(token, secret)).toThrow('invalid token type');
  });

  it('accepts access JWT when enforcement off', () => {
    delete process.env.BFF_REQUIRE_STREAM_TICKET;
    const token = jwt.sign({ sub: 'user-1' }, secret, { expiresIn: '15m' });
    expect(resolveUserIdFromToken(token, secret)).toBe('user-1');
  });
});
