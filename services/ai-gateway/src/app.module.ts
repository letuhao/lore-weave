import { Module } from '@nestjs/common';
import { FederationService } from './federation/federation.service.js';
import { AdminFederationService } from './federation/admin-federation.service.js';
import { AdminMcpController } from './mcp/admin-mcp.controller.js';
import { McpController } from './mcp/mcp.controller.js';
import { HealthController } from './health/health.controller.js';
import { GroundingController } from './grounding/grounding.controller.js';

@Module({
  // AdminMcpController is listed before McpController so the more-specific
  // `/mcp/admin` route is registered ahead of `/mcp` (INV-T6 — distinct surfaces).
  controllers: [AdminMcpController, McpController, HealthController, GroundingController],
  providers: [FederationService, AdminFederationService],
})
export class AppModule {}
