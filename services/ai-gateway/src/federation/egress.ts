import { lookup } from 'node:dns/promises';
import { isIP } from 'node:net';

/**
 * REG-P3-04 — egress control for the per-user overlay's outbound calls to a user's
 * registered (external) MCP server. A user-supplied endpoint is untrusted: it must
 * not reach the internal network / cloud metadata (SSRF), must stay on its declared
 * allowlist (incl. across redirects), must not return an unbounded body, and a
 * flapping server must not stall every turn (circuit breaker). Every failure surfaces
 * as a tool error to the model — never a silent hang.
 *
 * This is the RUNTIME counterpart to the registry's register-time SSRF guard + probe:
 * the same defenses re-applied at call time so a DNS rebind after registration cannot
 * smuggle the loop into an internal address.
 */

type FetchLike = (input: any, init?: any) => Promise<Response>;

// Mirror of the Go isBlockedIP (agent-registry security.go): loopback / RFC1918 /
// ULA / link-local (incl. 169.254.169.254 metadata) / CGNAT / unspecified.
export function isBlockedIp(ipRaw: string): boolean {
  const ip = ipRaw.trim();
  const v = isIP(ip);
  if (v === 4) {
    const p = ip.split('.').map((n) => parseInt(n, 10));
    if (p.length !== 4 || p.some((n) => Number.isNaN(n) || n < 0 || n > 255)) return true;
    const [a, b] = p;
    if (a === 0) return true; // 0.0.0.0/8 incl unspecified
    if (a === 10) return true; // RFC1918
    if (a === 127) return true; // loopback
    if (a === 169 && b === 254) return true; // link-local + metadata
    if (a === 172 && b >= 16 && b <= 31) return true; // RFC1918
    if (a === 192 && b === 168) return true; // RFC1918
    if (a === 100 && b >= 64 && b <= 127) return true; // CGNAT
    if (a >= 224) return true; // multicast / reserved
    return false;
  }
  if (v === 6) {
    const lo = ip.toLowerCase();
    if (lo === '::' || lo === '::1') return true; // unspecified / loopback
    if (lo.startsWith('fe80')) return true; // link-local
    if (lo.startsWith('fc') || lo.startsWith('fd')) return true; // ULA
    if (lo.startsWith('ff')) return true; // multicast
    // IPv4-mapped ::ffff:a.b.c.d → re-check the embedded v4
    const m = lo.match(/::ffff:(\d+\.\d+\.\d+\.\d+)$/);
    if (m) return isBlockedIp(m[1]);
    return false;
  }
  return true; // not an IP → treat as blocked (caller resolves names separately)
}

/** hostAllowed: the request host (hostname or host:port) must appear in the allowlist
 * (case-insensitive). An empty allowlist means "no allowlist configured" → allow (the
 * SSRF + isExternal checks still apply); a non-empty list is enforced strictly. */
export function hostAllowed(allowlist: string[], hostname: string, hostPort: string): boolean {
  if (!allowlist || allowlist.length === 0) return true;
  const set = new Set(allowlist.map((h) => h.toLowerCase()));
  return set.has(hostname.toLowerCase()) || set.has(hostPort.toLowerCase());
}

export interface EgressOptions {
  allowlist: string[];
  /** true for an internal loreweave server (dev/system) — skip the SSRF internal-block. */
  allowInternal: boolean;
  maxBytes: number;
  maxRedirects?: number;
}

/** Validate one URL against the SSRF + allowlist policy. Throws on violation. */
async function assertEgressAllowed(url: URL, opts: EgressOptions): Promise<void> {
  const host = url.hostname;
  const hostPort = url.host; // host:port
  if (!hostAllowed(opts.allowlist, host, hostPort)) {
    throw new Error(`egress blocked: ${hostPort} is not in the server's egress allowlist`);
  }
  if (opts.allowInternal) return; // trusted internal target
  // Literal IP → check directly; hostname → resolve ALL addresses and block if any internal.
  if (isIP(host)) {
    if (isBlockedIp(host)) throw new Error(`egress blocked: ${host} is an internal/metadata address`);
    return;
  }
  const addrs = await lookup(host, { all: true });
  if (addrs.length === 0) throw new Error(`egress blocked: ${host} did not resolve`);
  for (const a of addrs) {
    if (isBlockedIp(a.address)) throw new Error(`egress blocked: ${host} resolves to an internal address (${a.address})`);
  }
}

/** capBody wraps a response so reading past maxBytes errors the stream (bounded memory). */
function capBody(resp: Response, maxBytes: number): Response {
  const cl = resp.headers.get('content-length');
  if (cl && Number(cl) > maxBytes) {
    // Fail fast without reading.
    throw new Error(`egress blocked: response ${cl}B exceeds ${maxBytes}B cap`);
  }
  if (!resp.body) return resp;
  const reader = resp.body.getReader();
  let seen = 0;
  const capped = new ReadableStream({
    async pull(controller) {
      const { done, value } = await reader.read();
      if (done) {
        controller.close();
        return;
      }
      seen += value.byteLength;
      if (seen > maxBytes) {
        controller.error(new Error(`egress blocked: response exceeds ${maxBytes}B cap`));
        return;
      }
      controller.enqueue(value);
    },
    cancel(reason) {
      return reader.cancel(reason);
    },
  });
  return new Response(capped, { status: resp.status, statusText: resp.statusText, headers: resp.headers });
}

/** makeEgressFetch returns a FetchLike enforcing SSRF + allowlist + response cap +
 * manual redirect re-validation (a 3xx to an off-allowlist / internal host is blocked —
 * the round-3 redirect-SSRF defer). */
export function makeEgressFetch(opts: EgressOptions, base: FetchLike = fetch as any): FetchLike {
  const maxRedirects = opts.maxRedirects ?? 3;
  return async (input: any, init?: any): Promise<Response> => {
    let url = new URL(typeof input === 'string' ? input : input.url ?? String(input));
    let hops = 0;
    // Never let the underlying fetch auto-follow — we re-validate each hop.
    const reqInit = { ...(init ?? {}), redirect: 'manual' as const };
    while (true) {
      await assertEgressAllowed(url, opts);
      const resp = await base(url, reqInit);
      if (resp.status >= 300 && resp.status < 400 && resp.headers.get('location')) {
        if (hops++ >= maxRedirects) throw new Error('egress blocked: too many redirects');
        url = new URL(resp.headers.get('location')!, url);
        continue; // re-validate the redirect target next loop
      }
      return capBody(resp, opts.maxBytes);
    }
  };
}

/**
 * chooseOutboundHeaders — the tenancy boundary for a federated call. The internal
 * envelope (X-Internal-Token/X-User-Id) is trusted platform identity and goes ONLY to
 * internal loreweave servers. A third-party EXTERNAL server gets ONLY its own credential
 * (bearer/oauth), NEVER the internal token — leaking it would hand a third party our
 * service identity. External + no-auth → send nothing.
 */
export function chooseOutboundHeaders(
  isExternal: boolean,
  authKind: string,
  internalEnvelope: Record<string, string>,
  credential: string | null,
): Record<string, string> {
  if (!isExternal) return internalEnvelope;
  if ((authKind === 'bearer' || authKind === 'oauth2') && credential) {
    return { Authorization: `Bearer ${credential}` };
  }
  return {};
}

/** A per-server circuit breaker: after `threshold` consecutive failures the breaker
 * OPENS for `cooldownMs`; while open, requests fail fast (surfaced as a tool error,
 * never a hang). After the cooldown it half-opens (one trial); success closes it. */
export class CircuitBreaker {
  private readonly state = new Map<string, { failures: number; openUntil: number }>();
  constructor(private readonly threshold = 5, private readonly cooldownMs = 30_000, private readonly now: () => number = Date.now) {}

  canRequest(key: string): boolean {
    const s = this.state.get(key);
    if (!s) return true;
    if (s.openUntil === 0) return true; // closed
    return this.now() >= s.openUntil; // half-open trial allowed
  }

  isOpen(key: string): boolean {
    const s = this.state.get(key);
    return !!s && s.openUntil > 0 && this.now() < s.openUntil;
  }

  onSuccess(key: string): void {
    this.state.delete(key);
  }

  onFailure(key: string): void {
    const s = this.state.get(key) ?? { failures: 0, openUntil: 0 };
    s.failures += 1;
    if (s.failures >= this.threshold) {
      s.openUntil = this.now() + this.cooldownMs;
      s.failures = 0; // reset the counter for the next window after cooldown
    }
    this.state.set(key, s);
  }
}
