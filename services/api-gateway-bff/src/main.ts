// Phase 6c-γ — MUST be first: starts OpenTelemetry before @nestjs/core / http
// load so auto-instrumentation can patch them. No-op without OTEL_EXPORTER_OTLP_ENDPOINT.
import './tracing';

import { NestFactory } from '@nestjs/core';
import { WsAdapter } from '@nestjs/platform-ws';
import { AppModule } from './app.module';
import { configureGatewayApp } from './gateway-setup';

function requireEnv(key: string): string {
  const v = process.env[key];
  if (!v) throw new Error(`Required environment variable ${key} is not set`);
  return v;
}

async function bootstrap() {
  // Body must stream to auth-service; default JSON parser would consume /v1 bodies.
  const app = await NestFactory.create(AppModule, { bodyParser: false });
  app.useWebSocketAdapter(new WsAdapter(app));
  const authUrl = requireEnv('AUTH_SERVICE_URL');
  const bookUrl = requireEnv('BOOK_SERVICE_URL');
  const sharingUrl = requireEnv('SHARING_SERVICE_URL');
  const catalogUrl = requireEnv('CATALOG_SERVICE_URL');
  const providerRegistryUrl = requireEnv('PROVIDER_REGISTRY_SERVICE_URL');
  const usageBillingUrl = requireEnv('USAGE_BILLING_SERVICE_URL');
  const translationUrl = requireEnv('TRANSLATION_SERVICE_URL');
  const glossaryUrl = requireEnv('GLOSSARY_SERVICE_URL');
  const chatUrl = requireEnv('CHAT_SERVICE_URL');
  const roleplayUrl = requireEnv('ROLEPLAY_SERVICE_URL');
  const videoGenUrl = requireEnv('VIDEO_GEN_SERVICE_URL');
  const statisticsUrl = requireEnv('STATISTICS_SERVICE_URL');
  const notificationUrl = requireEnv('NOTIFICATION_SERVICE_URL');
  const knowledgeUrl = requireEnv('KNOWLEDGE_SERVICE_URL');
  const campaignUrl = requireEnv('CAMPAIGN_SERVICE_URL');
  const loreEnrichmentUrl = requireEnv('LORE_ENRICHMENT_SERVICE_URL');
  const learningUrl = requireEnv('LEARNING_SERVICE_URL');
  const compositionUrl = requireEnv('COMPOSITION_SERVICE_URL');
  const jobsUrl = requireEnv('JOBS_SERVICE_URL');
  // PUBLIC MCP edge — optional (the public surface is itself flag-gated in the edge),
  // so a default internal URL avoids forcing a new mandatory env on every deployment.
  const mcpPublicGatewayUrl = process.env.MCP_PUBLIC_GATEWAY_URL ?? 'http://mcp-public-gateway:8211';
  // KAL (knowledge-gateway) — the temporal-knowledge read boundary for the FE. Optional +
  // defaulted so existing deployments need no new mandatory env. The KAL dual-auths the
  // passed-through user JWT (validate + grant-check), so the BFF stays a dumb proxy here.
  const kalUrl = process.env.KNOWLEDGE_GATEWAY_URL ?? 'http://knowledge-gateway:3000';
  configureGatewayApp(app, { authUrl, bookUrl, sharingUrl, catalogUrl, providerRegistryUrl, usageBillingUrl, translationUrl, glossaryUrl, chatUrl, roleplayUrl, videoGenUrl, statisticsUrl, notificationUrl, knowledgeUrl, campaignUrl, loreEnrichmentUrl, learningUrl, compositionUrl, jobsUrl, mcpPublicGatewayUrl, kalUrl });

  app.enableShutdownHooks();
  const port = parseInt(process.env.PORT || '3000', 10);
  await app.listen(port);
  console.log(
    `api-gateway-bff listening on :${port} auth=${authUrl} books=${bookUrl} sharing=${sharingUrl} catalog=${catalogUrl} provider_registry=${providerRegistryUrl} usage_billing=${usageBillingUrl} translation=${translationUrl} glossary=${glossaryUrl} chat=${chatUrl} knowledge=${knowledgeUrl} composition=${compositionUrl}`,
  );
}
bootstrap();
