import { Controller, Get } from '@nestjs/common';
import { loadConfig } from '../config/config.js';

@Controller('health')
export class HealthController {
  private readonly cfg = loadConfig();

  @Get()
  health() {
    return { status: 'ok', service: 'knowledge-gateway' };
  }

  @Get('ready')
  ready() {
    return {
      status: 'ready',
      kgTemporal: this.cfg.kgTemporalEnabled ? 'ordinal_valid_time' : 'temporal_unsupported',
    };
  }
}
