import { createHash } from 'crypto';
import { ProviderConfig } from '../config/config.js';

/** One provider's federation outcome: its tools, or an error (→ partial catalog). */
export interface ProviderResult {
  provider: ProviderConfig;
  tools?: any[];
  error?: unknown;
}

/** Per-provider availability (H10) — lets a consumer's `find_tools` tell
 * "no such tool" from "owning provider temporarily down". */
export interface ProviderAvailability {
  name: string;
  available: boolean;
}

export interface Catalog {
  toolList: any[];
  toolToProvider: Map<string, ProviderConfig>;
  /** stable 16-hex hash of (name, inputSchema) pairs — H10 catalog version */
  version: string;
  /** true when ≥1 provider failed to list (H10 partial degradation) */
  partial: boolean;
  /** per-provider availability (H10) — `available=false` ⇒ that provider's tools
   * are temporarily missing from the catalog, NOT non-existent. */
  providers: ProviderAvailability[];
}

/**
 * Pure catalog assembly — no I/O, fully unit-testable. Merges provider tool
 * lists into one registry; first provider wins a name collision (H7); marks the
 * catalog partial if any provider errored, and records per-provider availability
 * (H10). Enforces the C-GW prefix rule: a tool whose name doesn't start with its
 * provider's `prefix` is DROPPED + warned (kills silent first-provider-wins
 * collisions). A provider with no `prefix` (legacy/unmapped) is not policed.
 *
 * @param results  per-provider federation outcomes
 * @param warn     sink for dropped-tool warnings (defaults to `console.warn`)
 */
export function computeCatalog(
  results: ProviderResult[],
  warn: (msg: string) => void = (m) => console.warn(m),
): Catalog {
  const map = new Map<string, ProviderConfig>();
  const tools: any[] = [];
  const providers: ProviderAvailability[] = [];
  let partial = false;

  for (const r of results) {
    if (r.error || !r.tools) {
      partial = true;
      providers.push({ name: r.provider.name, available: false });
      continue;
    }
    providers.push({ name: r.provider.name, available: true });
    // A provider may own MORE than one namespace (e.g. knowledge serves both
    // `memory_*` and `kg_*`); a tool is kept if it matches ANY allowed prefix.
    // No canonical prefix ⇒ empty allow-set ⇒ unpoliced (legacy/unmapped).
    const allowed = r.provider.prefix
      ? [r.provider.prefix, ...(r.provider.extraPrefixes ?? [])]
      : [];
    for (const t of r.tools) {
      if (!t || typeof t.name !== 'string') continue;
      // C-GW prefix enforcement: drop + warn a tool that escapes its namespace(s).
      if (allowed.length > 0 && !allowed.some((p) => t.name.startsWith(p))) {
        warn(
          `dropping tool '${t.name}' from provider '${r.provider.name}': ` +
            `name does not match any allowed prefix [${allowed.join(', ')}]`,
        );
        continue;
      }
      if (map.has(t.name)) continue; // collision — keep first
      map.set(t.name, r.provider);
      tools.push(t);
    }
  }

  tools.sort((a, b) => String(a.name).localeCompare(String(b.name)));
  const version = createHash('sha256')
    .update(JSON.stringify(tools.map((t) => [t.name, t.inputSchema])))
    .digest('hex')
    .slice(0, 16);

  return { toolList: tools, toolToProvider: map, version, partial, providers };
}

// ── Wave C5 — resources + prompts federation (the tools pattern, mirrored) ──

/** One provider's resources/prompts federation outcome. Any field a downstream
 * doesn't support (SDK capability assertion / -32601) arrives as `[]` — it
 * contributes nothing but never breaks the aggregate. `error` is set only when
 * the provider was unreachable outright. */
export interface ProviderAuxResult {
  provider: ProviderConfig;
  resources?: any[];
  resourceTemplates?: any[];
  prompts?: any[];
  error?: unknown;
}

/** The federated resources + prompts registry (sibling of {@link Catalog}). */
export interface AuxCatalog {
  resourceList: any[];
  resourceTemplateList: any[];
  promptList: any[];
  /** concrete resource URI → owning provider (resources/read routing) */
  resourceToProvider: Map<string, ProviderConfig>;
  /** prompt name → owning provider (prompts/get routing) */
  promptToProvider: Map<string, ProviderConfig>;
  /** URI scheme → provider — routes a TEMPLATE-instantiated URI (e.g.
   * `knowledge://project/<id>/summary`), which never appears in the concrete
   * map. Populated from every kept resource/template. */
  schemeToProvider: Map<string, ProviderConfig>;
}

export const EMPTY_AUX: AuxCatalog = {
  resourceList: [],
  resourceTemplateList: [],
  promptList: [],
  resourceToProvider: new Map(),
  promptToProvider: new Map(),
  schemeToProvider: new Map(),
};

/** Extract the scheme of a `scheme://...` URI (lowercased), or undefined. */
export function uriScheme(uri: string): string | undefined {
  const m = /^([a-z][a-z0-9+.-]*):\/\//i.exec(uri ?? '');
  return m ? m[1].toLowerCase() : undefined;
}

/**
 * Pure aggregation of the federated resources + prompts — no I/O, fully
 * unit-testable (mirrors {@link computeCatalog}).
 *
 * Namespacing (the C-GW rule, translated to each surface):
 *  • RESOURCES are namespaced by URI SCHEME, which must equal the provider's
 *    logical NAME (`knowledge://…` ⇐ provider `knowledge`) — a resource or
 *    template whose scheme escapes its provider is DROPPED + warned, exactly
 *    like a tool escaping its name prefix. The scheme also drives
 *    resources/read routing for template-instantiated URIs.
 *  • PROMPTS have no wire-level namespace (canonical prompt names like
 *    `recap_story_so_far` carry no provider prefix), so they get the
 *    pre-prefix-gate tools rule only: first provider wins a name collision.
 */
export function computeAuxCatalog(
  results: ProviderAuxResult[],
  warn: (msg: string) => void = (m) => console.warn(m),
): AuxCatalog {
  const resourceToProvider = new Map<string, ProviderConfig>();
  const promptToProvider = new Map<string, ProviderConfig>();
  const schemeToProvider = new Map<string, ProviderConfig>();
  const resourceList: any[] = [];
  const resourceTemplateList: any[] = [];
  const promptList: any[] = [];
  const seenTemplates = new Set<string>();

  for (const r of results) {
    if (r.error) continue; // unreachable → contributes nothing (H10 spirit)

    const keepScheme = (uri: string, what: string): string | undefined => {
      const scheme = uriScheme(uri);
      if (scheme !== r.provider.name) {
        warn(
          `dropping ${what} '${uri}' from provider '${r.provider.name}': ` +
            `URI scheme does not match the provider name`,
        );
        return undefined;
      }
      return scheme;
    };

    for (const res of r.resources ?? []) {
      const uri = res?.uri;
      if (typeof uri !== 'string') continue;
      const scheme = keepScheme(uri, 'resource');
      if (!scheme) continue;
      if (resourceToProvider.has(uri)) continue; // collision — keep first
      resourceToProvider.set(uri, r.provider);
      if (!schemeToProvider.has(scheme)) schemeToProvider.set(scheme, r.provider);
      resourceList.push(res);
    }

    for (const tpl of r.resourceTemplates ?? []) {
      const uriTemplate = tpl?.uriTemplate;
      if (typeof uriTemplate !== 'string') continue;
      const scheme = keepScheme(uriTemplate, 'resource template');
      if (!scheme) continue;
      if (seenTemplates.has(uriTemplate)) continue; // collision — keep first
      seenTemplates.add(uriTemplate);
      if (!schemeToProvider.has(scheme)) schemeToProvider.set(scheme, r.provider);
      resourceTemplateList.push(tpl);
    }

    for (const p of r.prompts ?? []) {
      if (!p || typeof p.name !== 'string') continue;
      if (promptToProvider.has(p.name)) continue; // collision — keep first
      promptToProvider.set(p.name, r.provider);
      promptList.push(p);
    }
  }

  resourceList.sort((a, b) => String(a.uri).localeCompare(String(b.uri)));
  resourceTemplateList.sort((a, b) => String(a.uriTemplate).localeCompare(String(b.uriTemplate)));
  promptList.sort((a, b) => String(a.name).localeCompare(String(b.name)));

  return {
    resourceList,
    resourceTemplateList,
    promptList,
    resourceToProvider,
    promptToProvider,
    schemeToProvider,
  };
}
