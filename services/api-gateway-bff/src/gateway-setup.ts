import type { INestApplication } from '@nestjs/common';
import { createProxyMiddleware } from 'http-proxy-middleware';
import type { Request, Response, NextFunction } from 'express';

/**
 * CORS, /v1 proxy to auth (streaming body), and GET /health.
 * Shared by main bootstrap and tests.
 */
export function configureGatewayApp(app: INestApplication, authUrl: string): void {
  app.enableCors({
    origin: true,
    credentials: true,
    allowedHeaders: ['Content-Type', 'Authorization'],
  });

  // Mount at `/` with a filter — if we used `use('/v1', proxy)`, Express would strip
  // `/v1` from req.url and the auth-service would receive `/auth/register` → 404.
  const proxy = createProxyMiddleware({
    target: authUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) => pathname.startsWith('/v1'),
  });

  const httpAdapter = app.getHttpAdapter();
  const instance = httpAdapter.getInstance();
  instance.use((req: Request, res: Response, next: NextFunction) =>
    (proxy as (req: Request, res: Response, next: NextFunction) => void)(req, res, next),
  );

  instance.get('/health', (_req: Request, res: Response) => {
    res.status(200).send('gateway ok');
  });
}
