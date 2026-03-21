import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { configureGatewayApp } from './gateway-setup';

async function bootstrap() {
  // Body must stream to auth-service; default JSON parser would consume /v1 bodies.
  const app = await NestFactory.create(AppModule, { bodyParser: false });
  const authUrl = process.env.AUTH_SERVICE_URL || 'http://localhost:8081';
  configureGatewayApp(app, authUrl);

  const port = parseInt(process.env.PORT || '3000', 10);
  await app.listen(port);
  console.log(`api-gateway-bff listening on :${port} -> ${authUrl}`);
}
bootstrap();
