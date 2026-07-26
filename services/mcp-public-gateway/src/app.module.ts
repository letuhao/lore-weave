import { Module } from '@nestjs/common';
import { PublicMcpController } from './mcp/public-mcp.controller.js';
import { HealthController } from './health/health.controller.js';
import { OAuthDiscoveryController } from './oauth/oauth-discovery.controller.js';

@Module({
  controllers: [PublicMcpController, HealthController, OAuthDiscoveryController],
})
export class AppModule {}
