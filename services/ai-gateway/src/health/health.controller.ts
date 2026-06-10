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

  /** H10 — the federated catalog version + partial flag, for consumers to poll. */
  @Get('catalog')
  catalog() {
    return {
      version: this.federation.catalogVersion(),
      tools: (this.federation.catalog() as unknown[]).length,
      providers: this.federation.providerCount(),
      partial: this.federation.isPartial(),
    };
  }
}
