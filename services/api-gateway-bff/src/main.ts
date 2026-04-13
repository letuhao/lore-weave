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
  const videoGenUrl = requireEnv('VIDEO_GEN_SERVICE_URL');
  const statisticsUrl = requireEnv('STATISTICS_SERVICE_URL');
  const notificationUrl = requireEnv('NOTIFICATION_SERVICE_URL');
  const knowledgeUrl = requireEnv('KNOWLEDGE_SERVICE_URL');
  configureGatewayApp(app, { authUrl, bookUrl, sharingUrl, catalogUrl, providerRegistryUrl, usageBillingUrl, translationUrl, glossaryUrl, chatUrl, videoGenUrl, statisticsUrl, notificationUrl, knowledgeUrl });

  app.enableShutdownHooks();
  const port = parseInt(process.env.PORT || '3000', 10);
  await app.listen(port);
  console.log(
    `api-gateway-bff listening on :${port} auth=${authUrl} books=${bookUrl} sharing=${sharingUrl} catalog=${catalogUrl} provider_registry=${providerRegistryUrl} usage_billing=${usageBillingUrl} translation=${translationUrl} glossary=${glossaryUrl} chat=${chatUrl} knowledge=${knowledgeUrl}`,
  );
}
bootstrap();
