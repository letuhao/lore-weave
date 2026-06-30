import 'reflect-metadata';
import { Logger } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module.js';
import { loadConfig } from './config/config.js';

async function bootstrap(): Promise<void> {
  const cfg = loadConfig();
  if (!cfg.internalToken) {
    // No hardcoded secrets — the KAL refuses to start without the token it presents to
    // the owning services' /internal routes. It must never run unable to authenticate downstream.
    Logger.error('FATAL: INTERNAL_SERVICE_TOKEN is required', 'bootstrap');
    process.exit(1);
  }
  const app = await NestFactory.create(AppModule);
  await app.listen(cfg.port, '0.0.0.0');
  Logger.log(
    `knowledge-gateway (KAL) on :${cfg.port} → glossary ${cfg.glossaryUrl} + knowledge ${cfg.knowledgeUrl} ` +
      `(KG temporal ${cfg.kgTemporalEnabled ? 'ENABLED' : 'unsupported'})`,
    'bootstrap',
  );
}

void bootstrap();
