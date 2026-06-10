import { Module } from '@nestjs/common';
import { FederationService } from './federation/federation.service.js';
import { McpController } from './mcp/mcp.controller.js';
import { HealthController } from './health/health.controller.js';
import { GroundingController } from './grounding/grounding.controller.js';

@Module({
  controllers: [McpController, HealthController, GroundingController],
  providers: [FederationService],
})
export class AppModule {}
