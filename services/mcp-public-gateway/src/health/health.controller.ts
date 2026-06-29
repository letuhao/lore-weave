import { Controller, Get } from '@nestjs/common';
import { loadConfig } from '../config/config.js';

@Controller('health')
export class HealthController {
  private readonly cfg = loadConfig();

  @Get()
  health() {
    return { status: 'ok' };
  }

  @Get('ready')
  ready() {
    // Public MCP is intentionally OFF until the Q-GATE flag is set — surface it
    // so ops can see why external traffic is being refused.
    return { status: 'ready', publicMcpEnabled: this.cfg.featureEnabled };
  }
}
