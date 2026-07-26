import {
  computeAuxCatalog,
  ProviderAuxResult,
  uriScheme,
} from '../src/federation/catalog.js';
import { FederationService } from '../src/federation/federation.service.js';
import { ProviderConfig } from '../src/config/config.js';

// Wave C5 — the resources + prompts federation (the tools pattern, mirrored).

const knowledge: ProviderConfig = { name: 'knowledge', mcpUrl: 'http://k/mcp' };
const glossary: ProviderConfig = { name: 'glossary', mcpUrl: 'http://g/mcp' };

const res = (uri: string) => ({ uri, name: uri, mimeType: 'text/plain' });
const tpl = (uriTemplate: string) => ({ uriTemplate, name: uriTemplate, mimeType: 'text/plain' });
const prompt = (name: string) => ({ name, description: name, arguments: [] });

describe('uriScheme', () => {
  it('extracts the scheme of a scheme://... URI, lowercased', () => {
    expect(uriScheme('knowledge://project/p1/summary')).toBe('knowledge');
    expect(uriScheme('KNOWLEDGE://x')).toBe('knowledge');
  });
  it('is undefined for a scheme-less or malformed URI', () => {
    expect(uriScheme('no-scheme-here')).toBeUndefined();
    expect(uriScheme('')).toBeUndefined();
    expect(uriScheme(undefined as unknown as string)).toBeUndefined();
  });
});

describe('computeAuxCatalog', () => {
  it('aggregates resources, templates, and prompts across providers, sorted', () => {
    const c = computeAuxCatalog([
      {
        provider: knowledge,
        resources: [res('knowledge://b'), res('knowledge://a')],
        resourceTemplates: [tpl('knowledge://project/{project_id}/summary')],
        prompts: [prompt('recap_story_so_far')],
      },
      {
        provider: glossary,
        resources: [res('glossary://standards')],
        resourceTemplates: [],
        prompts: [prompt('entity_dossier')],
      },
    ]);
    expect(c.resourceList.map((r) => r.uri)).toEqual([
      'glossary://standards',
      'knowledge://a',
      'knowledge://b',
    ]);
    expect(c.resourceTemplateList.map((t) => t.uriTemplate)).toEqual([
      'knowledge://project/{project_id}/summary',
    ]);
    expect(c.promptList.map((p) => p.name)).toEqual(['entity_dossier', 'recap_story_so_far']);
    expect(c.resourceToProvider.get('knowledge://a')).toBe(knowledge);
    expect(c.promptToProvider.get('entity_dossier')).toBe(glossary);
    expect(c.schemeToProvider.get('knowledge')).toBe(knowledge);
    expect(c.schemeToProvider.get('glossary')).toBe(glossary);
  });

  it('drops + warns a resource whose URI scheme escapes its provider (C-GW mirror)', () => {
    const warnings: string[] = [];
    const c = computeAuxCatalog(
      [
        {
          provider: glossary,
          // A glossary provider must not claim the knowledge:// namespace.
          resources: [res('knowledge://sneaky'), res('glossary://ok')],
          resourceTemplates: [tpl('knowledge://also/{sneaky}')],
          prompts: [],
        },
      ],
      (m) => warnings.push(m),
    );
    expect(c.resourceList.map((r) => r.uri)).toEqual(['glossary://ok']);
    expect(c.resourceTemplateList).toEqual([]);
    expect(warnings).toHaveLength(2);
    expect(warnings[0]).toContain('knowledge://sneaky');
  });

  it('an errored (unreachable) provider contributes empty lists, never breaks the aggregate', () => {
    const c = computeAuxCatalog([
      { provider: knowledge, error: new Error('down') },
      { provider: glossary, resources: [res('glossary://ok')], prompts: [prompt('p')] },
    ]);
    expect(c.resourceList.map((r) => r.uri)).toEqual(['glossary://ok']);
    expect(c.promptList.map((p) => p.name)).toEqual(['p']);
  });

  it('a downstream without the capability (empty/absent lists) contributes nothing', () => {
    const results: ProviderAuxResult[] = [
      { provider: knowledge, resources: [], resourceTemplates: [], prompts: [] },
      { provider: glossary }, // fields entirely absent
    ];
    const c = computeAuxCatalog(results);
    expect(c.resourceList).toEqual([]);
    expect(c.resourceTemplateList).toEqual([]);
    expect(c.promptList).toEqual([]);
  });

  it('keeps the first provider on a prompt name collision (H7 mirror)', () => {
    const c = computeAuxCatalog([
      { provider: knowledge, prompts: [prompt('dup')] },
      { provider: glossary, prompts: [prompt('dup')] },
    ]);
    expect(c.promptList).toHaveLength(1);
    expect(c.promptToProvider.get('dup')).toBe(knowledge);
  });
});

describe('FederationService resource/prompt routing (round-trip)', () => {
  const aux = computeAuxCatalog([
    {
      provider: knowledge,
      resources: [res('knowledge://static')],
      resourceTemplates: [tpl('knowledge://project/{project_id}/summary')],
      prompts: [prompt('recap_story_so_far')],
    },
  ]);
  const svc = new FederationService();
  (svc as unknown as { auxState: typeof aux }).auxState = aux;

  it('routes a concrete catalog URI to its owning provider', () => {
    expect(svc.providerForResource('knowledge://static')).toBe(knowledge);
  });

  it('routes a TEMPLATE-instantiated URI by scheme (never in the concrete map)', () => {
    expect(svc.providerForResource('knowledge://project/p-123/summary')).toBe(knowledge);
  });

  it('unknown scheme / scheme-less URI resolves no provider', () => {
    expect(svc.providerForResource('mystery://x')).toBeUndefined();
    expect(svc.providerForResource('not-a-uri')).toBeUndefined();
  });

  it('routes a prompt name to its owning provider; unknown name resolves none', () => {
    expect(svc.providerForPrompt('recap_story_so_far')).toBe(knowledge);
    expect(svc.providerForPrompt('nope')).toBeUndefined();
  });
});
