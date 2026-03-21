import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { configureGatewayApp } from './gateway-setup';

async function bootstrap() {
  // Body must stream to auth-service; default JSON parser would consume /v1 bodies.
  const app = await NestFactory.create(AppModule, { bodyParser: false });
  const authUrl = process.env.AUTH_SERVICE_URL || 'http://localhost:8081';
  const bookUrl = process.env.BOOK_SERVICE_URL || 'http://localhost:8082';
  const sharingUrl = process.env.SHARING_SERVICE_URL || 'http://localhost:8083';
  const catalogUrl = process.env.CATALOG_SERVICE_URL || 'http://localhost:8084';
  const providerRegistryUrl = process.env.PROVIDER_REGISTRY_SERVICE_URL || 'http://localhost:8085';
  const usageBillingUrl = process.env.USAGE_BILLING_SERVICE_URL || 'http://localhost:8086';
  configureGatewayApp(app, { authUrl, bookUrl, sharingUrl, catalogUrl, providerRegistryUrl, usageBillingUrl });

  const port = parseInt(process.env.PORT || '3000', 10);
  await app.listen(port);
  console.log(
    `api-gateway-bff listening on :${port} auth=${authUrl} books=${bookUrl} sharing=${sharingUrl} catalog=${catalogUrl} provider_registry=${providerRegistryUrl} usage_billing=${usageBillingUrl}`,
  );
}
bootstrap();
