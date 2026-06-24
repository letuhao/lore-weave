// External (non-model) BYOK services — the "lạc loài" of the model registry.
//
// Capabilities like `web_search` are NOT models: there is no model to pick, no
// inventory to sync, no per-token pricing — just an external endpoint + key the
// user brings (BYOK), reached through provider-registry exactly like a model
// credential (the provider-gateway invariant). They are registered via the
// "External Services" section instead of the model "Add Model" flow.
//
// To add a new such service (e.g. the documented forward `web_fetch`), append one
// entry here — the ExternalServicesCard + AddServiceModal are fully data-driven.

export type ServiceType = {
  /**
   * The capability-flag token AND the provider_kind used for the credential.
   * Must match the value the BE resolves on (e.g. `web_search` → provider-registry
   * /internal/web-search filters capability_flags {"web_search": true}).
   */
  key: string;
  /** Lucide icon name rendered in the card (kept as a string to avoid a hard dep here). */
  icon: 'search' | 'globe';
  /** Placeholder shown in the endpoint field (illustrative, not a default). */
  endpointPlaceholder: string;
  /** Whether the backend can run without a secret (e.g. a keyless local SearXNG). */
  keyless: boolean;
};

export const SERVICE_TYPES: ServiceType[] = [
  {
    key: 'web_search',
    icon: 'search',
    endpointPlaceholder: 'http://local-web-search-service:8090',
    keyless: true,
  },
];

/** Provider-kinds owned by the External Services section (excluded from the LLM provider list). */
export const SERVICE_KINDS: ReadonlySet<string> = new Set(SERVICE_TYPES.map((s) => s.key));

/** Capability-flag tokens that mark a user_model as an external service (not a model). */
export const SERVICE_CAPABILITIES: ReadonlySet<string> = new Set(SERVICE_TYPES.map((s) => s.key));

export function getServiceType(key: string): ServiceType | undefined {
  return SERVICE_TYPES.find((s) => s.key === key);
}

/** True when a provider credential belongs to the External Services section. */
export function isServiceProvider(providerKind: string): boolean {
  return SERVICE_KINDS.has(providerKind);
}
