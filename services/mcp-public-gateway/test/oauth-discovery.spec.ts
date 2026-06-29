import {
  authServerBaseFromResource,
  protectedResourceMetadata,
  resourceMetadataUrl,
  wwwAuthenticateChallenge,
} from '../src/oauth/discovery.js';

const RES = 'https://app.loreweave.dev/mcp';

describe('oauth discovery helpers', () => {
  it('derives the AS base by stripping the /mcp suffix + trailing slashes', () => {
    expect(authServerBaseFromResource(RES)).toBe('https://app.loreweave.dev');
    expect(authServerBaseFromResource('https://app.loreweave.dev/mcp/')).toBe('https://app.loreweave.dev');
    expect(authServerBaseFromResource('https://x.dev')).toBe('https://x.dev'); // no /mcp suffix → unchanged
  });

  it('builds the PRM doc pointing at the AS base + advertising the scope vocab', () => {
    const doc = protectedResourceMetadata(RES) as {
      resource: string;
      authorization_servers: string[];
      bearer_methods_supported: string[];
      scopes_supported: string[];
    };
    expect(doc.resource).toBe(RES);
    expect(doc.authorization_servers).toEqual(['https://app.loreweave.dev']);
    expect(doc.bearer_methods_supported).toEqual(['header']);
    expect(doc.scopes_supported).toContain('read');
    expect(doc.scopes_supported).toContain('domain:catalog');
  });

  it('an empty resource yields a valid-but-empty authorization_servers list', () => {
    const doc = protectedResourceMetadata('') as { authorization_servers: string[] };
    expect(doc.authorization_servers).toEqual([]);
  });

  it('builds the resource-metadata URL + the WWW-Authenticate challenge', () => {
    expect(resourceMetadataUrl(RES)).toBe('https://app.loreweave.dev/.well-known/oauth-protected-resource');
    expect(wwwAuthenticateChallenge(RES)).toBe(
      'Bearer resource_metadata="https://app.loreweave.dev/.well-known/oauth-protected-resource"',
    );
  });
});
