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

  const proxy = createProxyMiddleware({
    target: authUrl,
    changeOrigin: true,
    pathRewrite: (path) => path,
  });

  const httpAdapter = app.getHttpAdapter();
  const instance = httpAdapter.getInstance();
  instance.use('/v1', (req: Request, res: Response, next: NextFunction) =>
    (proxy as (req: Request, res: Response, next: NextFunction) => void)(req, res, next),
  );

  instance.get('/health', (_req: Request, res: Response) => {
    res.status(200).send('gateway ok');
  });
}
