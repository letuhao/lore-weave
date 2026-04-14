import type { INestApplication } from '@nestjs/common';
import { createProxyMiddleware } from 'http-proxy-middleware';
import type { Request, Response, NextFunction } from 'express';
import type { Socket } from 'net';

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
    chatUrl: string;
    videoGenUrl: string;
    statisticsUrl: string;
    notificationUrl: string;
    knowledgeUrl: string;
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
      pathname.startsWith('/v1/auth') || pathname.startsWith('/v1/account') || pathname.startsWith('/v1/me/preferences') || pathname.startsWith('/v1/users'),
  });
  const bookProxy = createProxyMiddleware({
    target: urls.bookUrl,
    changeOrigin: true,
    // Allow large bodies for cover image upload (multipart/form-data)
    selfHandleResponse: false,
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
  const extractionProxy = createProxyMiddleware({
    target: urls.translationUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/extraction'),
  });
  const glossaryProxy = createProxyMiddleware({
    target: urls.glossaryUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/glossary'),
  });
  const chatProxy = createProxyMiddleware({
    target: urls.chatUrl,
    changeOrigin: true,
    // Disable body buffering so SSE streams pass through immediately
    selfHandleResponse: false,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/chat'),
  });
  const videoGenProxy = createProxyMiddleware({
    target: urls.videoGenUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/video-gen'),
  });
  const statisticsProxy = createProxyMiddleware({
    target: urls.statisticsUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) =>
      pathname.startsWith('/v1/leaderboard') || pathname.startsWith('/v1/stats'),
  });
  const notificationProxy = createProxyMiddleware({
    target: urls.notificationUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/notifications'),
  });
  const knowledgeProxy = createProxyMiddleware({
    target: urls.knowledgeUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/knowledge'),
    // K-CLEAN-5 (Gate-5-I4 + D-K8-04): when knowledge-service is
    // unreachable (container down, DNS, refused) http-proxy-middleware
    // would otherwise propagate the upstream connection error as a
    // generic 500 with a stack trace. Convert it to a structured 503
    // so the FE can distinguish "backend down — show degraded UI"
    // from "real bug — show error toast." Headers may already be
    // sent if the error fires mid-stream; guard against double-send.
    on: {
      error: (
        err: NodeJS.ErrnoException,
        req: Request,
        res: Response | Socket,
      ) => {
        // For WebSocket upgrades the proxy passes the raw Socket
        // — we don't have an Express Response to render JSON onto,
        // just close the socket cleanly.
        if (!('status' in res) || typeof res.status !== 'function') {
          try {
            (res as Socket).destroy?.();
          } catch {
            // ignore
          }
          return;
        }
        const httpRes = res as Response;
        if (httpRes.headersSent) {
          try {
            httpRes.end();
          } catch {
            // socket likely already destroyed
          }
          return;
        }
        const traceId =
          (req.headers['x-trace-id'] as string | undefined) ?? null;
        httpRes.status(503).set('Content-Type', 'application/json');
        if (traceId) {
          httpRes.set('X-Trace-Id', traceId);
        }
        httpRes.end(
          JSON.stringify({
            detail: 'knowledge_service_unavailable',
            code: err?.code ?? 'ECONNREFUSED',
            trace_id: traceId,
          }),
        );
      },
    },
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
  const extractionProxyFn = extractionProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  const glossaryProxyFn = glossaryProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  const chatProxyFn = chatProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  const videoGenProxyFn = videoGenProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  const statisticsProxyFn = statisticsProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  const notificationProxyFn = notificationProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  const knowledgeProxyFn = knowledgeProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  instance.use((req: Request, res: Response, next: NextFunction) => {
    if (req.path.startsWith('/v1/auth') || req.path.startsWith('/v1/account') || req.path.startsWith('/v1/me/preferences') || req.path.startsWith('/v1/users')) {
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
    if (req.path.startsWith('/v1/extraction')) {
      return extractionProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/translation')) {
      return translationProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/glossary')) {
      return glossaryProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/chat')) {
      return chatProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/video-gen')) {
      return videoGenProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/leaderboard') || req.path.startsWith('/v1/stats')) {
      return statisticsProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/notifications')) {
      return notificationProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/knowledge')) {
      return knowledgeProxyFn(req, res, next);
    }
    return next();
  });

  instance.get('/health', (_req: Request, res: Response) => {
    res.status(200).send('gateway ok');
  });
}
