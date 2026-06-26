import { Module } from '@nestjs/common';
import { PublicMcpController } from './mcp/public-mcp.controller.js';
import { HealthController } from './health/health.controller.js';

@Module({
  controllers: [PublicMcpController, HealthController],
})
export class AppModule {}
