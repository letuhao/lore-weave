import { UnauthorizedException, ExecutionContext } from '@nestjs/common';
import { resetConfigForTest } from '../src/config/config.js';
import { InternalTokenGuard } from '../src/auth/internal-token.guard.js';

function ctxWith(headers: Record<string, string | undefined>): ExecutionContext {
  return {
    switchToHttp: () => ({ getRequest: () => ({ headers }) }),
  } as unknown as ExecutionContext;
}

describe('InternalTokenGuard (HIGH-1 inbound auth)', () => {
  const orig = process.env.INTERNAL_SERVICE_TOKEN;
  beforeEach(() => {
    process.env.INTERNAL_SERVICE_TOKEN = 'secret-tok';
    resetConfigForTest();
  });
  afterEach(() => {
    if (orig === undefined) delete process.env.INTERNAL_SERVICE_TOKEN;
    else process.env.INTERNAL_SERVICE_TOKEN = orig;
    resetConfigForTest();
  });

  const guard = new InternalTokenGuard();

  it('admits a request presenting the correct X-Internal-Token', () => {
    expect(guard.canActivate(ctxWith({ 'x-internal-token': 'secret-tok' }))).toBe(true);
  });

  it('rejects a missing token (no unauthenticated access)', () => {
    expect(() => guard.canActivate(ctxWith({}))).toThrow(UnauthorizedException);
  });

  it('rejects a wrong token (no impersonation via spoofed X-User-Id)', () => {
    expect(() => guard.canActivate(ctxWith({ 'x-internal-token': 'nope', 'x-user-id': 'attacker' }))).toThrow(
      UnauthorizedException,
    );
  });
});
