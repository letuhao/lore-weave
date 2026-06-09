import 'reflect-metadata';
import { Logger } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module.js';
import { loadConfig } from './config/config.js';

async function bootstrap(): Promise<void> {
  const cfg = loadConfig();
  if (!cfg.internalToken) {
    // No hardcoded secrets — the service refuses to start without its token.
    Logger.error('FATAL: INTERNAL_SERVICE_TOKEN is required', 'bootstrap');
    process.exit(1);
  }
  const app = await NestFactory.create(AppModule);
  await app.listen(cfg.port, '0.0.0.0');
  Logger.log(
    `ai-gateway on :${cfg.port} — federating [${cfg.providers.map((p) => p.name).join(', ')}]`,
    'bootstrap',
  );
}

void bootstrap();
