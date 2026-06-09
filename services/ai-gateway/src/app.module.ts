import { Module } from '@nestjs/common';
import { FederationService } from './federation/federation.service.js';
import { McpController } from './mcp/mcp.controller.js';
import { HealthController } from './health/health.controller.js';

@Module({
  controllers: [McpController, HealthController],
  providers: [FederationService],
})
export class AppModule {}
