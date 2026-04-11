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
    chatUrl: string;
    videoGenUrl: string;
    statisticsUrl: string;
    notificationUrl: string;
    audioServiceUrl: string;
    audioServiceApiKey: string;
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

  // Audio service proxy (TTS/STT) — optional, returns 503 if not configured
  const audioServiceConfigured = !!urls.audioServiceUrl;
  const audioServiceApiKey = urls.audioServiceApiKey || '';
  const audioProxy = audioServiceConfigured
    ? createProxyMiddleware({
        target: urls.audioServiceUrl,
        changeOrigin: true,
        // Allow streaming audio responses (chunked transfer for TTS)
        selfHandleResponse: false,
        pathFilter: (pathname: string) => pathname.startsWith('/v1/audio'),
        // Swap user JWT for the audio service's own API key
        on: audioServiceApiKey ? {
          proxyReq: (proxyReq) => {
            proxyReq.setHeader('Authorization', `Bearer ${audioServiceApiKey}`);
          },
        } : undefined,
      })
    : null;

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
  const audioProxyFn = audioProxy as unknown as ((
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void) | null;

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
    if (req.path.startsWith('/v1/audio')) {
      if (!audioProxyFn) {
        return res.status(503).json({ code: 'AUDIO_SERVICE_UNAVAILABLE', message: 'Audio service not configured. Set AUDIO_SERVICE_URL to enable TTS/STT.' });
      }
      return audioProxyFn(req, res, next);
    }
    return next();
  });

  instance.get('/health', (_req: Request, res: Response) => {
    res.status(200).send('gateway ok');
  });
}
