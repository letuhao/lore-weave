import { Controller, Get } from '@nestjs/common';
import { FederationService } from '../federation/federation.service.js';

@Controller('health')
export class HealthController {
  constructor(private readonly federation: FederationService) {}

  @Get()
  health() {
    return { status: 'ok' };
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
