import 'reflect-metadata';
import { Logger } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module.js';
import { loadConfig } from './config/config.js';

async function bootstrap(): Promise<void> {
  const cfg = loadConfig();
  if (!cfg.internalToken) {
    // No hardcoded secrets — the edge refuses to start without the token it mints
    // toward ai-gateway (PUB-2). It must never run without being able to authenticate downstream.
    Logger.error('FATAL: INTERNAL_SERVICE_TOKEN is required', 'bootstrap');
    process.exit(1);
  }
  const app = await NestFactory.create(AppModule);
  await app.listen(cfg.port, '0.0.0.0');
  Logger.log(
    `mcp-public-gateway on :${cfg.port} → relays to ${cfg.aiGatewayUrl}/mcp ` +
      `(public MCP ${cfg.featureEnabled ? 'ENABLED' : 'DISABLED'})`,
    'bootstrap',
  );
}

void bootstrap();
