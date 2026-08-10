import { Controller, Get } from '@nestjs/common';
import { temporalCapability } from '../kal/temporal.js';

@Controller('health')
export class HealthController {

  @Get()
  health() {
    return { status: 'ok', service: 'knowledge-gateway' };
  }

  @Get('ready')
  async ready() {
    // T26 — found by `scripts/gateway-domain-logic-gate.py` on its first real run. This
    // computed the KG's temporal capability from the GATEWAY's own config, the same bug as
    // the old `temporalCapability()`, and in the worst possible place: a readiness probe
    // that operators trust to describe the deployment. A gateway could report
    // `ordinal_valid_time` here while the knowledge-service it fronts had no such thing.
    return { status: 'ready', kgTemporal: (await temporalCapability()).kg };
  }
}
