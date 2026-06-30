/**
 * knowledge-gateway (KAL) configuration — env-driven, no hardcoded secrets.
 *
 * The KAL federates the two owning services behind one typed contract. It holds the
 * internal service token and presents X-Internal-Token + X-User-Id downstream; it never
 * exposes that token to callers.
 */
export interface AppConfig {
  port: number;
  /** service-to-service token presented to glossary/knowledge `/internal/*` routes. */
  internalToken: string;
  /** HS256 secret for validating a FE user's Bearer JWT (dual-auth user mode). Same platform
   *  secret glossary/knowledge use. Empty disables user mode (internal-token only). */
  jwtSecret: string;
  /** book-service base URL — the grant authority. In user mode the KAL grant-checks
   *  (user has access to the book) before forwarding, since the BFF is a dumb passthrough. */
  bookServiceUrl: string;
  /** glossary-service base URL (SSOT projection of entity_facts + the fact write routes). */
  glossaryUrl: string;
  /** knowledge-service base URL (the Neo4j KG). */
  knowledgeUrl: string;
  /**
   * Whether the KG branch carries a unified story-ordinal valid-time (foundation F3).
   * Gates per-substrate `as_of` (§12.5.1 / A5): until true the KG reports
   * `temporal_unsupported`. F3 has landed, so the default is true; the env override exists
   * for a deployment whose knowledge-service predates the F3 migration.
   */
  kgTemporalEnabled: boolean;
}

let cached: AppConfig | undefined;

export function loadConfig(): AppConfig {
  if (cached) return cached;
  cached = {
    port: parseInt(process.env.PORT ?? '3000', 10),
    internalToken: process.env.INTERNAL_SERVICE_TOKEN ?? '',
    jwtSecret: process.env.JWT_SECRET ?? '',
    bookServiceUrl: process.env.BOOK_SERVICE_URL ?? 'http://book-service:8082',
    glossaryUrl: process.env.GLOSSARY_SERVICE_URL ?? 'http://glossary-service:8088',
    knowledgeUrl: process.env.KNOWLEDGE_SERVICE_URL ?? 'http://knowledge-service:8000',
    kgTemporalEnabled: (process.env.KG_TEMPORAL_ENABLED ?? 'true') !== 'false',
  };
  return cached;
}

/** Test-only: reset the memoized config so env changes take effect. */
export function resetConfigForTest(): void {
  cached = undefined;
}
