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
    const prefix = r.provider.prefix;
    for (const t of r.tools) {
      if (!t || typeof t.name !== 'string') continue;
      // C-GW prefix enforcement: drop + warn a tool that escapes its namespace.
      if (prefix && !t.name.startsWith(prefix)) {
        warn(
          `dropping tool '${t.name}' from provider '${r.provider.name}': ` +
            `name does not match required prefix '${prefix}'`,
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
