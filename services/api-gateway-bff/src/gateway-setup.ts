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
    roleplayUrl: string;
    videoGenUrl: string;
    statisticsUrl: string;
    notificationUrl: string;
    knowledgeUrl: string;
    campaignUrl: string;
    loreEnrichmentUrl: string;
    learningUrl: string;
    compositionUrl: string;
    jobsUrl: string;
    /** PUBLIC MCP edge; optional + defaulted so existing callers/tests need no change. */
    mcpPublicGatewayUrl?: string;
  },
): void {
  const mcpPublicGatewayUrl = urls.mcpPublicGatewayUrl ?? 'http://mcp-public-gateway:8211';
  app.enableCors({
    origin: true,
    credentials: true,
    // D-K8-03: `If-Match` carries the weak ETag the FE captured on
    // GET. Without an explicit entry here the CORS preflight
    // (OPTIONS) rejects any PATCH that includes it, even though
    // the actual verb would have been allowed.
    // MCP fan-out: `x-loreweave-stream-format` is the AG-UI stream-format
    // negotiation header the chat FE sends on /chat messages + tool-results.
    // The entire MCP-fanout FE runs on the agui surface, so a cross-origin
    // deployment is broken without this (preflight rejects the POST). Found by
    // the COMPOSE-C browser pass.
    allowedHeaders: ['Content-Type', 'Authorization', 'If-Match', 'x-loreweave-stream-format'],
    // ETag is a response header, not a request header. Browsers
    // expose a small default set (Content-Type, etc.) to JS; any
    // non-default header must be explicitly exposed. The FE only
    // needs ETag for round-tripping but exposing it anyway keeps
    // the API usable from non-LoreWeave frontends.
    exposedHeaders: ['ETag'],
  });

  const authProxy = createProxyMiddleware({
    target: urls.authUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) =>
      pathname.startsWith('/v1/auth') || pathname.startsWith('/v1/account') || pathname.startsWith('/v1/me/preferences') || pathname.startsWith('/v1/users') || pathname.startsWith('/v1/admin') ||
      // P5 OAuth 2.1 — the authorization server lives in auth-service (RFC 8414 AS
      // metadata + the /oauth/* endpoints). External OAuth traffic still flows through
      // the BFF edge (gateway invariant).
      pathname === '/.well-known/oauth-authorization-server' || pathname.startsWith('/oauth/'),
  });
  const bookProxy = createProxyMiddleware({
    target: urls.bookUrl,
    changeOrigin: true,
    // Allow large bodies for cover image upload (multipart/form-data)
    selfHandleResponse: false,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/books'),
  });
  // C21 — thin `/v1/worlds*` passthrough to book-service (worlds + bible
  // provisioning live in book-service, same target as `/v1/books`). This is a
  // gateway-invariant enabling passthrough only — NO world business logic in the
  // gateway; it just forwards. Mirrors bookProxy exactly.
  const worldsProxy = createProxyMiddleware({
    target: urls.bookUrl,
    changeOrigin: true,
    selfHandleResponse: false,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/worlds'),
  });
  // MCP-fanout C-CONFIRM seam fix (live-pass): the generic confirm card commits a
  // book Tier-W/S action via `/v1/book/actions/{preview,confirm}` (SINGULAR
  // `book`, the domain enum used by confirm_action). bookProxy only matches
  // `/v1/books` (plural), so this pair fell through to a 404 and the book confirm
  // round-trip never completed. Thin passthrough to book-service, same target.
  const bookActionsProxy = createProxyMiddleware({
    target: urls.bookUrl,
    changeOrigin: true,
    selfHandleResponse: false,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/book/actions'),
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
  // MCP-fanout C-CONFIRM seam fix (live-pass): the generic confirm card commits a
  // settings Tier-W/S action (e.g. set a default model) via
  // `/v1/settings/actions/{preview,confirm}` on provider-registry. There was no
  // `/v1/settings` proxy (the service is otherwise reached at `/v1/model-registry`),
  // so the settings confirm round-trip 404'd. Thin passthrough, same target.
  const settingsActionsProxy = createProxyMiddleware({
    target: urls.providerRegistryUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/settings/actions'),
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
  const glossaryTranslateProxy = createProxyMiddleware({
    target: urls.translationUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/glossary-translate'),
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
  // roleplay-service (Rust) — scripts + start-orchestration. A normal domain
  // REST proxy (gateway invariant holds); roleplay-service validates the JWT
  // itself (like book-service), so Authorization passes through unchanged. The
  // path is forwarded verbatim — roleplay-service serves `/v1/roleplay/*`.
  const roleplayProxy = createProxyMiddleware({
    target: urls.roleplayUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/roleplay'),
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
    // Phase 2e — `/v1/notifications/stream` is served LOCALLY by
    // NotificationsController as an SSE bridge over RabbitMQ events;
    // exclude it from the upstream proxy so the NestJS handler runs.
    pathFilter: (pathname: string) =>
      pathname.startsWith('/v1/notifications') &&
      pathname !== '/v1/notifications/stream',
  });
  const knowledgeProxy = createProxyMiddleware({
    target: urls.knowledgeUrl,
    changeOrigin: true,
    // Both /v1/knowledge (projects, entities, …) AND /v1/kg (the KG customizable-
    // ontology surface: graph-schemas, adopt, views, sync, triage) live on
    // knowledge-service — the FE ontologyApi targets /v1/kg. (D-KG-ONTOLOGY-FE-WIRING:
    // the BFF previously proxied only /v1/knowledge, so every /v1/kg call 404'd.)
    pathFilter: (pathname: string) =>
      pathname.startsWith('/v1/knowledge') || pathname.startsWith('/v1/kg'),
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
  // Auto-Draft Factory S1 — campaign-service (saga orchestrator API).
  const campaignProxy = createProxyMiddleware({
    target: urls.campaignUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/campaigns'),
  });

  const loreEnrichmentProxy = createProxyMiddleware({
    target: urls.loreEnrichmentUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/lore-enrichment'),
  });

  // Unified Job Control Plane P2 — jobs-service (/v1/jobs list/detail + SSE
  // stream). `selfHandleResponse:false` (default) so GET /v1/jobs/stream passes
  // through un-buffered, the chat/composition SSE precedent.
  const jobsProxy = createProxyMiddleware({
    target: urls.jobsUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/jobs'),
  });

  // PUBLIC MCP edge — the SECOND public entry class (external agents), distinct
  // from the /v1 REST surface. `/mcp` (NOT /v1-prefixed; MCP is unversioned) →
  // mcp-public-gateway, which authenticates the agent's API key, strips inbound
  // x-* (PUB-9), mints the internal envelope, and relays to ai-gateway/mcp ONLY.
  // selfHandleResponse:false so MCP streamable-HTTP (SSE) passes un-buffered.
  const mcpPublicProxy = createProxyMiddleware({
    target: mcpPublicGatewayUrl,
    changeOrigin: true,
    selfHandleResponse: false,
    // `/mcp*` plus the P5 RFC 9728 Protected Resource Metadata (served by the resource = the edge).
    pathFilter: (pathname: string) =>
      pathname === '/mcp' ||
      pathname.startsWith('/mcp/') ||
      pathname === '/.well-known/oauth-protected-resource',
  });

  // Phase B — learning-service (Axis-1 correction read API).
  const learningProxy = createProxyMiddleware({
    target: urls.learningUrl,
    changeOrigin: true,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/learning'),
  });

  // LOOM M7 — composition-service (co-writer). `selfHandleResponse:false` so the
  // POST /v1/composition/works/{id}/generate SSE stream passes through
  // un-buffered (chat precedent). 503-on-down mirrors knowledgeProxy so the FE
  // can show "backend down" vs a real error.
  const compositionProxy = createProxyMiddleware({
    target: urls.compositionUrl,
    changeOrigin: true,
    selfHandleResponse: false,
    pathFilter: (pathname: string) => pathname.startsWith('/v1/composition'),
    on: {
      error: (
        err: NodeJS.ErrnoException,
        req: Request,
        res: Response | Socket,
      ) => {
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
            detail: 'composition_service_unavailable',
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
  const worldsProxyFn = worldsProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  const bookActionsProxyFn = bookActionsProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  const settingsActionsProxyFn = settingsActionsProxy as unknown as (
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
  const glossaryTranslateProxyFn = glossaryTranslateProxy as unknown as (
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
  const roleplayProxyFn = roleplayProxy as unknown as (
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
  const campaignProxyFn = campaignProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  const loreEnrichmentProxyFn = loreEnrichmentProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  const learningProxyFn = learningProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  const compositionProxyFn = compositionProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  const jobsProxyFn = jobsProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  const mcpPublicProxyFn = mcpPublicProxy as unknown as (
    req: Request,
    res: Response,
    next: NextFunction,
  ) => void;
  instance.use((req: Request, res: Response, next: NextFunction) => {
    // PUBLIC MCP (unversioned, external-agent entry) — matched before the /v1 chain.
    // Includes the P5 RFC 9728 Protected Resource Metadata served by the edge.
    if (req.path === '/mcp' || req.path.startsWith('/mcp/') || req.path === '/.well-known/oauth-protected-resource') {
      return mcpPublicProxyFn(req, res, next);
    }
    // P5 OAuth authorization server (RFC 8414 AS metadata + /oauth/*) → auth-service.
    if (
      req.path.startsWith('/v1/auth') || req.path.startsWith('/v1/account') || req.path.startsWith('/v1/me/preferences') || req.path.startsWith('/v1/users') || req.path.startsWith('/v1/admin') ||
      req.path === '/.well-known/oauth-authorization-server' || req.path.startsWith('/oauth/')
    ) {
      return authProxyFn(req, res, next);
    }
    // MCP-fanout C-CONFIRM: `/v1/book/actions/*` (singular) → book-service. Must
    // precede the `/v1/books` (plural) check; the two are disjoint but keeping the
    // generic-confirm action route first documents the intent.
    if (req.path.startsWith('/v1/book/actions')) {
      return bookActionsProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/books')) {
      return bookProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/worlds')) {
      return worldsProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/sharing')) {
      return sharingProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/catalog')) {
      return catalogProxyFn(req, res, next);
    }
    // MCP-fanout C-CONFIRM: `/v1/settings/actions/*` → provider-registry (the
    // settings domain commit path for the generic confirm card).
    if (req.path.startsWith('/v1/settings/actions')) {
      return settingsActionsProxyFn(req, res, next);
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
    if (req.path.startsWith('/v1/glossary-translate')) {
      return glossaryTranslateProxyFn(req, res, next);
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
    if (req.path.startsWith('/v1/roleplay')) {
      return roleplayProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/video-gen')) {
      return videoGenProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/leaderboard') || req.path.startsWith('/v1/stats')) {
      return statisticsProxyFn(req, res, next);
    }
    if (
      req.path.startsWith('/v1/notifications') &&
      req.path !== '/v1/notifications/stream'
    ) {
      return notificationProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/knowledge') || req.path.startsWith('/v1/kg')) {
      return knowledgeProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/campaigns')) {
      return campaignProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/learning')) {
      return learningProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/composition')) {
      return compositionProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/lore-enrichment')) {
      return loreEnrichmentProxyFn(req, res, next);
    }
    if (req.path.startsWith('/v1/jobs')) {
      return jobsProxyFn(req, res, next);
    }
    return next();
  });

  instance.get('/health', (_req: Request, res: Response) => {
    res.status(200).send('gateway ok');
  });
}
