import { Controller, Get, Res } from '@nestjs/common';
import type { Response } from 'express';
import { FederationService } from '../federation/federation.service.js';

@Controller('health')
export class HealthController {
  constructor(private readonly federation: FederationService) {}

  /**
   * LIVENESS only — deliberately independent of federation state.
   *
   * This is what the docker healthcheck polls, and it must NOT fail on a partial
   * catalog: `glossary-service` declares `depends_on: ai-gateway:
   * condition: service_healthy` (infra/docker-compose.yml), so an unhealthy gateway
   * would DEADLOCK a down provider out of ever restarting — glossary down → gateway
   * unhealthy → glossary can never come back. The outage signal lives on
   * {@link federation} instead, which is loud without being load-bearing.
   */
  @Get()
  health() {
    return { status: 'ok' };
  }

  /**
   * Federation degradation — the ALERTING signal (outage visibility, 2026-07-23).
   * Returns **503** once the catalog has been PARTIAL for `federationDegradedAfterRefreshes`
   * consecutive refreshes, so a poller/alert can fire on status code alone; 200 otherwise.
   *
   * Sustained-not-instant on purpose: a single missed refresh during a routine provider
   * restart is normal and must not page anyone. **Do not wire this to a docker/k8s
   * healthcheck** — see {@link health} for the deadlock that causes.
   *
   * Exists because a provider could vanish from the catalog with no machine-readable
   * signal anywhere: `/health` said ok, the container read healthy, and the only trace
   * was a WARN line reprinted every 30s. The glossary de-federation ran undetected until
   * a live E2E tripped over it.
   */
  @Get('federation')
  federationHealth(@Res({ passthrough: true }) res: Response) {
    const status = this.federation.federationStatus();
    res.status(status.degraded ? 503 : 200);
    return {
      status: status.degraded ? 'degraded' : 'ok',
      ...status,
      providers: this.federation.providerAvailability(),
    };
  }

  @Get('ready')
  ready() {
    return { status: 'ready', catalogVersion: this.federation.catalogVersion() };
  }

  /**
   * H10 — federated catalog version + partial flag + per-provider availability,
   * for consumers to poll. `providers` is the array `[{name, available}]` that a
   * consumer's find_tools reads to distinguish "no such tool" from "owning
   * provider temporarily down" (→ say "try again", not "I can't"). `providerCount`
   * keeps the prior scalar for back-compat.
   */
  @Get('catalog')
  catalog() {
    return {
      version: this.federation.catalogVersion(),
      tools: (this.federation.catalog() as unknown[]).length,
      providerCount: this.federation.providerCount(),
      providers: this.federation.providerAvailability(),
      partial: this.federation.isPartial(),
    };
  }
}
