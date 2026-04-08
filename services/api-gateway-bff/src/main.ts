import { NestFactory } from '@nestjs/core';
import { WsAdapter } from '@nestjs/platform-ws';
import { AppModule } from './app.module';
import { configureGatewayApp } from './gateway-setup';

async function bootstrap() {
  // Body must stream to auth-service; default JSON parser would consume /v1 bodies.
  const app = await NestFactory.create(AppModule, { bodyParser: false });
  app.useWebSocketAdapter(new WsAdapter(app));
  const authUrl = process.env.AUTH_SERVICE_URL || 'http://localhost:8081';
  const bookUrl = process.env.BOOK_SERVICE_URL || 'http://localhost:8082';
  const sharingUrl = process.env.SHARING_SERVICE_URL || 'http://localhost:8083';
  const catalogUrl = process.env.CATALOG_SERVICE_URL || 'http://localhost:8084';
  const providerRegistryUrl = process.env.PROVIDER_REGISTRY_SERVICE_URL || 'http://localhost:8085';
  const usageBillingUrl = process.env.USAGE_BILLING_SERVICE_URL || 'http://localhost:8086';
  const translationUrl = process.env.TRANSLATION_SERVICE_URL || 'http://localhost:8087';
  const glossaryUrl = process.env.GLOSSARY_SERVICE_URL || 'http://localhost:8088';
  const chatUrl = process.env.CHAT_SERVICE_URL || 'http://localhost:8090';
  const videoGenUrl = process.env.VIDEO_GEN_SERVICE_URL || 'http://localhost:8088';
  const statisticsUrl = process.env.STATISTICS_SERVICE_URL || 'http://localhost:8089';
  configureGatewayApp(app, { authUrl, bookUrl, sharingUrl, catalogUrl, providerRegistryUrl, usageBillingUrl, translationUrl, glossaryUrl, chatUrl, videoGenUrl, statisticsUrl });

  const port = parseInt(process.env.PORT || '3000', 10);
  await app.listen(port);
  console.log(
    `api-gateway-bff listening on :${port} auth=${authUrl} books=${bookUrl} sharing=${sharingUrl} catalog=${catalogUrl} provider_registry=${providerRegistryUrl} usage_billing=${usageBillingUrl} translation=${translationUrl} glossary=${glossaryUrl} chat=${chatUrl}`,
  );
}
bootstrap();
