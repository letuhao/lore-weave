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

  it('rejects an EMPTY presented token when the secret is unset (misconfig fails closed)', () => {
    /* The `!expected` clause, and this is the only case that exercises it. Written as the
       tempting `presented !== expected`, the guard still rejects a MISSING header even with
       no secret configured — `config.ts:37` coerces the unset var with `?? ''`, so the
       comparison is `undefined !== ''`, which is true. That near-miss is what makes the
       branch look untestable and is why the first draft of this test passed with the clause
       DELETED, proving nothing.
       The hole is an empty-VALUED header: `'' !== ''` is false, so the guard returns true and
       all eight destructive write routes — merge, split, purge, fold, restore, reassign-kind,
       episodes, resolve-entity — admit an unauthenticated caller, whose X-User-Id is then
       trusted as the tenancy identity. `curl -H 'X-Internal-Token;'` sends exactly that. */
    delete process.env.INTERNAL_SERVICE_TOKEN;
    resetConfigForTest();
    expect(() => guard.canActivate(ctxWith({ 'x-internal-token': '' }))).toThrow(
      UnauthorizedException,
    );
  });

  it('an empty token is refused even when the secret IS configured', () => {
    /* The control arm: the case above must fail because the secret is missing, not because
       the empty string is special-cased somewhere. This one passes with or without the
       clause — recorded as a companion, not as evidence for it. */
    expect(() => guard.canActivate(ctxWith({ 'x-internal-token': '' }))).toThrow(
      UnauthorizedException,
    );
  });
});
