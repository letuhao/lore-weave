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

  // DRIFT-LOCK: this array mirrors the `Domain` union. Adding a domain to the union without
  // adding it here goes red — deliberately. A new domain is a public ENTITLEMENT decision
  // (which keys may reach its tools), not a typing detail. `research` was added by Track D
  // CD5 for the universal `web_search`.
  it('counts ALL of TOOL_POLICY for a broad scope holding every tier + every domain', () => {
    const allTiers = ['read', 'paid_read', 'write_auto', 'write_confirm'];
    const domains: Domain[] = ['book', 'glossary', 'knowledge', 'translation', 'composition', 'jobs', 'settings', 'lore_enrichment', 'catalog', 'story', 'registry', 'research'];
    const allDomains = domains.map(domainScope);
    const scopes = [...allTiers, ...allDomains];
    expect(scopeToolCount(scopes)).toBe(Object.keys(TOOL_POLICY).length);
    expect(scopeToolCount(scopes)).toBeGreaterThanOrEqual(DIRECT_LIST_TOOL_THRESHOLD);
  });

  it('reaches web_search only with domain:research — a glossary-scoped key keeps the legacy alias', () => {
    // The rename is deliberately NOT transparent at the public edge: `web_search` lives in
    // the `research` domain, so a key already issued for `domain:glossary` cannot reach it.
    // That is precisely why `glossary_web_search` is demoted-in-place rather than deleted —
    // dropping its TOOL_POLICY row would 403 every key already in the wild.
    const glossaryKey = ['paid_read', domainScope('glossary')];
    expect(isToolAllowed('glossary_web_search', glossaryKey)).toBe(true);
    expect(isToolAllowed('web_search', glossaryKey)).toBe(false);

    const researchKey = ['paid_read', domainScope('research')];
    expect(isToolAllowed('web_search', researchKey)).toBe(true);
    expect(isToolAllowed('glossary_web_search', researchKey)).toBe(false);

    // paid_read is required — a plain `read` key must never be able to spend money.
    expect(isToolAllowed('web_search', ['read', domainScope('research')])).toBe(false);
  });

  it('returns 0 for a scope with no domain grant (fail-closed, matches isToolAllowed)', () => {
    expect(scopeToolCount(['read', 'write_auto', 'write_confirm'])).toBe(0);
  });

  // Discovery-hardening plan item 8 / external audit #6 — story_search was a real, live tool
  // on the authenticated chat surface but had no TOOL_POLICY entry at all (the `story` domain
  // didn't even exist in the Domain union), so no public key — however privileged — could ever
  // reach it. Closed by adding the `story` domain + a read-tier entry.
  it('story_search is reachable with read + domain:story, and denied without it', () => {
    expect(isToolAllowed('story_search', ['read', domainScope('story')])).toBe(true);
    expect(isToolAllowed('story_search', ['read'])).toBe(false);
    expect(isToolAllowed('story_search', [domainScope('story')])).toBe(false);
  });

  // MED-1 review finding — registry_list_skills/registry_get_skill (agent-registry-service)
  // had no TOOL_POLICY entry at all (no `registry` Domain member either), the exact same
  // incomplete-rollout shape as the `story` gap above. Closed by adding the `registry`
  // domain + read-tier entries for the two reads and write_auto entries for the three
  // propose/update/toggle tools (all Tier-A/ScopeUser upstream — propose/update mint a
  // pending human-approved proposal, never a direct write; set_skill_enabled is a
  // reversible per-user toggle).
  it('registry_list_skills / registry_get_skill are reachable with read + domain:registry, and denied without it', () => {
    expect(isToolAllowed('registry_list_skills', ['read', domainScope('registry')])).toBe(true);
    expect(isToolAllowed('registry_get_skill', ['read', domainScope('registry')])).toBe(true);
    expect(isToolAllowed('registry_list_skills', ['read'])).toBe(false);
    expect(isToolAllowed('registry_get_skill', [domainScope('registry')])).toBe(false);
  });

  it('registry write tools (propose/update/toggle) require write_auto + domain:registry', () => {
    const writeScopes = ['write_auto', domainScope('registry')];
    expect(isToolAllowed('registry_propose_skill', writeScopes)).toBe(true);
    expect(isToolAllowed('registry_update_skill', writeScopes)).toBe(true);
    expect(isToolAllowed('registry_set_skill_enabled', writeScopes)).toBe(true);
    // read-only scope cannot reach the write tools
    expect(isToolAllowed('registry_propose_skill', ['read', domainScope('registry')])).toBe(false);
    // write_auto scope without the registry domain grant cannot reach them either
    expect(isToolAllowed('registry_update_skill', ['write_auto'])).toBe(false);
    expect(isToolAllowed('registry_set_skill_enabled', ['write_auto'])).toBe(false);
  });

  it('the wildcard scope trivially "counts" the whole allowlist — production code must never route it here', () => {
    // Documents the 8b.7 contract at the unit level: calling scopeToolCount with `*` is not
    // wrong in isolation (it's a pure function), but per spec the wildcard branch in
    // public-mcp.controller.ts is a distinct, EARLIER check that never reaches this function.
    expect(scopeToolCount([WILDCARD_SCOPE])).toBe(Object.keys(TOOL_POLICY).length);
  });
});
