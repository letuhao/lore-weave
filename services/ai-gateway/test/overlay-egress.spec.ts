import { isBlockedIp, hostAllowed, makeEgressFetch, CircuitBreaker, chooseOutboundHeaders } from '../src/federation/egress.js';

describe('REG-P3-04 egress SSRF IP block', () => {
  it('blocks loopback / RFC1918 / metadata / ULA / CGNAT', () => {
    for (const ip of ['127.0.0.1', '10.0.0.5', '172.16.3.4', '192.168.1.1', '169.254.169.254', '0.0.0.0', '100.100.0.1', '::1', 'fd00::1', 'fe80::1', '::ffff:127.0.0.1']) {
      expect(isBlockedIp(ip)).toBe(true);
    }
  });
  it('allows public addresses', () => {
    for (const ip of ['93.184.216.34', '8.8.8.8', '2606:2800:220:1::']) {
      expect(isBlockedIp(ip)).toBe(false);
    }
  });
});

describe('REG-P3-04 egress allowlist', () => {
  it('empty allowlist allows anything (SSRF still applies elsewhere)', () => {
    expect(hostAllowed([], 'evil.com', 'evil.com:443')).toBe(true);
  });
  it('non-empty allowlist enforces strictly (host or host:port)', () => {
    expect(hostAllowed(['mcp.example.com:8443'], 'mcp.example.com', 'mcp.example.com:8443')).toBe(true);
    expect(hostAllowed(['mcp.example.com'], 'mcp.example.com', 'mcp.example.com:443')).toBe(true);
    expect(hostAllowed(['mcp.example.com'], 'evil.com', 'evil.com:443')).toBe(false);
  });
});

describe('REG-P3-04 egress fetch policy', () => {
  it('blocks a literal internal target when not allowInternal', async () => {
    const ef = makeEgressFetch({ allowlist: [], allowInternal: false, maxBytes: 1024 }, async () => new Response('x'));
    await expect(ef('http://169.254.169.254/latest/meta-data')).rejects.toThrow(/internal|metadata/i);
  });
  it('blocks a host not in a non-empty allowlist', async () => {
    const ef = makeEgressFetch({ allowlist: ['good.com'], allowInternal: true, maxBytes: 1024 }, async () => new Response('x'));
    await expect(ef('https://evil.com/mcp')).rejects.toThrow(/allowlist/i);
  });
  it('allows an internal target under allowInternal (dev/system)', async () => {
    const base = jest.fn(async () => new Response('ok', { status: 200 }));
    const ef = makeEgressFetch({ allowlist: [], allowInternal: true, maxBytes: 1024 }, base as any);
    const r = await ef('http://127.0.0.1:9000/mcp');
    expect(r.status).toBe(200);
    expect(base).toHaveBeenCalled();
  });
  it('rejects a body over the size cap via content-length', async () => {
    const base = async () => new Response('x', { status: 200, headers: { 'content-length': '9999' } });
    const ef = makeEgressFetch({ allowlist: [], allowInternal: true, maxBytes: 10 }, base as any);
    await expect(ef('http://127.0.0.1/mcp')).rejects.toThrow(/cap/i);
  });
  it('strips the Authorization credential on a cross-origin redirect', async () => {
    const seen: Array<{ url: string; auth: string | null }> = [];
    const base = async (url: any, init?: any) => {
      seen.push({ url: String(url), auth: new Headers(init?.headers ?? {}).get('authorization') });
      if (String(url).includes('a.example')) return new Response(null, { status: 302, headers: { location: 'https://b.example/x' } });
      return new Response('ok');
    };
    const ef = makeEgressFetch({ allowlist: [], allowInternal: true, maxBytes: 1024 }, base as any);
    await ef('https://a.example/start', { headers: { authorization: 'Bearer user-secret' } });
    expect(seen[0].auth).toBe('Bearer user-secret'); // original request keeps it
    expect(seen[1].auth).toBeNull(); // cross-origin redirect must NOT carry it
  });

  it('re-validates a redirect target and blocks a redirect to an internal host', async () => {
    const base = jest.fn(async (url: any) => {
      if (String(url).includes('start')) {
        return new Response(null, { status: 302, headers: { location: 'http://169.254.169.254/' } });
      }
      return new Response('ok');
    });
    const ef = makeEgressFetch({ allowlist: [], allowInternal: false, maxBytes: 1024 }, base as any);
    await expect(ef('https://93.184.216.34/start')).rejects.toThrow(/internal|metadata/i);
  });
});

describe('REG-P3-03/04 outbound-header tenancy boundary', () => {
  const envelope = { 'X-Internal-Token': 'SECRET-INTERNAL', 'X-User-Id': 'u1' };
  it('internal server gets the internal envelope', () => {
    const h = chooseOutboundHeaders(false, 'none', envelope, null);
    expect(h['X-Internal-Token']).toBe('SECRET-INTERNAL');
  });
  it('external server NEVER receives the internal token', () => {
    const bearer = chooseOutboundHeaders(true, 'bearer', envelope, 'user-token-abc');
    expect(bearer['X-Internal-Token']).toBeUndefined();
    expect(bearer['Authorization']).toBe('Bearer user-token-abc');
    const none = chooseOutboundHeaders(true, 'none', envelope, null);
    expect(none['X-Internal-Token']).toBeUndefined();
    expect(Object.keys(none)).toHaveLength(0);
  });
  it('external oauth2 uses the fetched access token', () => {
    const h = chooseOutboundHeaders(true, 'oauth2', envelope, 'oauth-access-1');
    expect(h['Authorization']).toBe('Bearer oauth-access-1');
    expect(h['X-Internal-Token']).toBeUndefined();
  });
});

describe('REG-P3-04 circuit breaker', () => {
  it('opens after threshold failures and half-opens after cooldown', () => {
    let now = 1000;
    const cb = new CircuitBreaker(3, 500, () => now);
    expect(cb.canRequest('s')).toBe(true);
    cb.onFailure('s');
    cb.onFailure('s');
    expect(cb.isOpen('s')).toBe(false); // 2 < 3
    cb.onFailure('s'); // 3rd → open
    expect(cb.isOpen('s')).toBe(true);
    expect(cb.canRequest('s')).toBe(false);
    now += 600; // past cooldown
    expect(cb.canRequest('s')).toBe(true); // half-open trial
    cb.onSuccess('s');
    expect(cb.isOpen('s')).toBe(false);
    expect(cb.canRequest('s')).toBe(true);
  });

  it('RE-OPENS when the half-open trial itself fails (does not stay half-open forever)', () => {
    let now = 1000;
    const cb = new CircuitBreaker(3, 500, () => now);
    cb.onFailure('s'); cb.onFailure('s'); cb.onFailure('s'); // → open
    expect(cb.isOpen('s')).toBe(true);
    now += 600; // cooldown elapsed → half-open
    expect(cb.canRequest('s')).toBe(true);
    cb.onFailure('s'); // the trial FAILS → must immediately re-open
    expect(cb.isOpen('s')).toBe(true);
    expect(cb.canRequest('s')).toBe(false);
  });
});
