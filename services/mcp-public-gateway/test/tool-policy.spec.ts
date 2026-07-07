import { domainScope, isToolAllowed, scopeToolCount, TOOL_POLICY, DIRECT_LIST_TOOL_THRESHOLD, WILDCARD_SCOPE, type Domain } from '../src/scope/tool-policy.js';

// Scope-size-adaptive exposure (2026-07-07 spec §3.3/§6/§8b.7): `scopeToolCount` is the
// pure input to mcp-public-gateway's tools/list branch (public-mcp.controller.ts) — count
// how many TOOL_POLICY entries a given scope set resolves to.
describe('tool-policy.scopeToolCount', () => {
  it('counts exactly the book-read tools for a narrow read+domain:book scope', () => {
    const scopes = ['read', domainScope('book')];
    const expected = Object.keys(TOOL_POLICY).filter((n) => isToolAllowed(n, scopes));
    // book-read-only is a small, real-world scope (measured §3.3) — assert the concrete
    // count (5) AND that it matches the brute-force filter, so a TOOL_POLICY edit that
    // changes book's read-tool count is caught by BOTH assertions, not silently drifting.
    expect(scopeToolCount(scopes)).toBe(5);
    expect(scopeToolCount(scopes)).toBe(expected.length);
    expect(scopeToolCount(scopes)).toBeLessThan(DIRECT_LIST_TOOL_THRESHOLD);
  });

  it('counts exactly the knowledge-read tools for a narrow read+domain:knowledge scope', () => {
    const scopes = ['read', domainScope('knowledge')];
    expect(scopeToolCount(scopes)).toBe(11);
    expect(scopeToolCount(scopes)).toBeLessThan(DIRECT_LIST_TOOL_THRESHOLD);
  });

  it('counts ALL of TOOL_POLICY for a broad scope holding every tier + every domain', () => {
    const allTiers = ['read', 'paid_read', 'write_auto', 'write_confirm'];
    const domains: Domain[] = ['book', 'glossary', 'knowledge', 'translation', 'composition', 'jobs', 'settings', 'lore_enrichment', 'catalog'];
    const allDomains = domains.map(domainScope);
    const scopes = [...allTiers, ...allDomains];
    expect(scopeToolCount(scopes)).toBe(Object.keys(TOOL_POLICY).length);
    expect(scopeToolCount(scopes)).toBeGreaterThanOrEqual(DIRECT_LIST_TOOL_THRESHOLD);
  });

  it('returns 0 for a scope with no domain grant (fail-closed, matches isToolAllowed)', () => {
    expect(scopeToolCount(['read', 'write_auto', 'write_confirm'])).toBe(0);
  });

  it('the wildcard scope trivially "counts" the whole allowlist — production code must never route it here', () => {
    // Documents the 8b.7 contract at the unit level: calling scopeToolCount with `*` is not
    // wrong in isolation (it's a pure function), but per spec the wildcard branch in
    // public-mcp.controller.ts is a distinct, EARLIER check that never reaches this function.
    expect(scopeToolCount([WILDCARD_SCOPE])).toBe(Object.keys(TOOL_POLICY).length);
  });
});
