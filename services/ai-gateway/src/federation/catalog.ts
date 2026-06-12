import { createHash } from 'crypto';
import { ProviderConfig } from '../config/config.js';

/** One provider's federation outcome: its tools, or an error (→ partial catalog). */
export interface ProviderResult {
  provider: ProviderConfig;
  tools?: any[];
  error?: unknown;
}

export interface Catalog {
  toolList: any[];
  toolToProvider: Map<string, ProviderConfig>;
  /** stable 16-hex hash of (name, inputSchema) pairs — H10 catalog version */
  version: string;
  /** true when ≥1 provider failed to list (H10 partial degradation) */
  partial: boolean;
}

/**
 * Pure catalog assembly — no I/O, fully unit-testable. Merges provider tool
 * lists into one registry; first provider wins a name collision (H7 — never
 * happens with one provider; provider-prefixing lands with provider #2);
 * marks the catalog partial if any provider errored.
 */
export function computeCatalog(results: ProviderResult[]): Catalog {
  const map = new Map<string, ProviderConfig>();
  const tools: any[] = [];
  let partial = false;

  for (const r of results) {
    if (r.error || !r.tools) {
      partial = true;
      continue;
    }
    for (const t of r.tools) {
      if (!t || typeof t.name !== 'string') continue;
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

  return { toolList: tools, toolToProvider: map, version, partial };
}
