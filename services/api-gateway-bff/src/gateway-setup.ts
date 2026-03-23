import type { INestApplication } from '@nestjs/common';
import { createProxyMiddleware } from 'http-proxy-middleware';
import type { Request, Response, NextFunction } from 'express';

/**
 * CORS, /v1 proxy by domain, and GET /health.
 * Shared by main bootstrap and tests.
 */
export function configureGatewayApp(
  app: INestApplication,
  urls: {
    authUrl: string;
    bookUrl: string;
    sharingUrl: string;
    catalogUrl: string;
    providerRegistryUrl: string;
    usageBillingUrl: string;
    translationUrl: string;
    glossaryUrl: string;
  },
): void {
  app.enableCors({
    origin: true,
    credentials: true,
    allowedHeaders: ['Content-Type', 'Authorization'],
  });

  const authProxy = createProxyMiddleware({
    target: urls.authUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) =>
      pathname.startsWith('/v1/auth') || pathname.startsWith('/v1/account'),
  });
  const bookProxy = createProxyMiddleware({
    target: urls.bookUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/books'),
  });
  const sharingProxy = createProxyMiddleware({
    target: urls.sharingUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/sharing'),
  });
  const catalogProxy = createProxyMiddleware({
    target: urls.catalogUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/catalog'),
  });
  const providerRegistryProxy = createProxyMiddleware({
    target: urls.providerRegistryUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/model-registry'),
  });
  const usageBillingProxy = createProxyMiddleware({
    target: urls.usageBillingUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/model-billing'),
  });
  const translationProxy = createProxyMiddleware({
    target: urls.translationUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/translation'),
  });
  const glossaryProxy = createProxyMiddleware({
    target: urls.glossaryUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/glossary'),
  });

  const httpAdapter = app.getHttpAdapter();
  const instance = httpAdapter.getInstance();
  const authProxyFn = authProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  const bookProxyFn = bookProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  const sharingProxyFn = sharingProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  const catalogProxyFn = catalogProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  const providerRegistryProxyFn = providerRegistryProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  const usageBillingProxyFn = usageBillingProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  const translationProxyFn = translationProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  const glossaryProxyFn = glossaryProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;

  instance.use((req: Request, res: Response, next: NextFunction) => {
    if (req.path.startsWith('/v1/auth') || req.path.startsWith('/v1/account')) {
      return authProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/books')) {
      return bookProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/sharing')) {
      return sharingProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/catalog')) {
      return catalogProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/model-registry')) {
      return providerRegistryProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/model-billing')) {
      return usageBillingProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/translation')) {
      return translationProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/glossary')) {
      return glossaryProxyFn(req, res, next);
    }
    return next();
  });

  instance.get('/health', (_req: Request, res: Response) => {
    res.status(200).send('gateway ok');
  });
}
