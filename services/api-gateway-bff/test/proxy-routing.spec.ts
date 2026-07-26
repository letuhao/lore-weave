import { INestApplication } from '@nestjs/common';
import { Test, TestingModule } from '@nestjs/testing';
import { WsAdapter } from '@nestjs/platform-ws';
import * as request from 'supertest';
import * as http from 'http';
import { AddressInfo } from 'net';
import { AppModule } from '../src/app.module';
import { configureGatewayApp } from '../src/gateway-setup';

function startUpstream(marker: string) {
  const server = http.createServer((_req, res) => {
    res.statusCode = 200;
    res.setHeader('Content-Type', 'text/plain');
    res.end(marker);
  });
  return new Promise<http.Server>((resolve) => {
    server.listen(0, () => resolve(server));
  });
}

function urlOf(server: http.Server) {
  const addr = server.address() as AddressInfo;
  return `http://127.0.0.1:${addr.port}`;
}

describe('Gateway proxy routing', () => {
  let app: INestApplication;
  let authServer: http.Server;
  let bookServer: http.Server;
  let sharingServer: http.Server;
  let catalogServer: http.Server;
  let providerRegistryServer: http.Server;
  let usageBillingServer: http.Server;
  let translationServer: http.Server;
  let glossaryServer: http.Server;
  let chatServer: http.Server;
  let roleplayServer: http.Server;
  let videoGenServer: http.Server;
  let statisticsServer: http.Server;
  let notificationServer: http.Server;
  let knowledgeServer: http.Server;
  let loreEnrichmentServer: http.Server;
  let mcpPublicServer: http.Server;

  beforeAll(async () => {
    [
      authServer,
      bookServer,
      sharingServer,
      catalogServer,
      providerRegistryServer,
      usageBillingServer,
      translationServer,
      glossaryServer,
      chatServer,
      roleplayServer,
      videoGenServer,
      statisticsServer,
      notificationServer,
      knowledgeServer,
      loreEnrichmentServer,
      mcpPublicServer,
    ] = await Promise.all([
      startUpstream('auth'),
      startUpstream('books'),
      startUpstream('sharing'),
      startUpstream('catalog'),
      startUpstream('provider-registry'),
      startUpstream('usage-billing'),
      startUpstream('translation'),
      startUpstream('glossary'),
      startUpstream('chat'),
      startUpstream('roleplay'),
      startUpstream('video-gen'),
      startUpstream('statistics'),
      startUpstream('notification'),
      startUpstream('knowledge'),
      startUpstream('lore-enrichment'),
      startUpstream('mcp-public'),
    ]);

    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();
    app = moduleFixture.createNestApplication({ bodyParser: false });
    app.useWebSocketAdapter(new WsAdapter(app));
    configureGatewayApp(app, {
      authUrl: urlOf(authServer),
      bookUrl: urlOf(bookServer),
      sharingUrl: urlOf(sharingServer),
      catalogUrl: urlOf(catalogServer),
      providerRegistryUrl: urlOf(providerRegistryServer),
      usageBillingUrl: urlOf(usageBillingServer),
      translationUrl: urlOf(translationServer),
      glossaryUrl: urlOf(glossaryServer),
      chatUrl: urlOf(chatServer),
      roleplayUrl: urlOf(roleplayServer),
      videoGenUrl: urlOf(videoGenServer),
      statisticsUrl: urlOf(statisticsServer),
      notificationUrl: urlOf(notificationServer),
      knowledgeUrl: urlOf(knowledgeServer),
      // S1 — not asserted by these routing tests; a valid URL to satisfy the type.
      campaignUrl: urlOf(knowledgeServer),
      loreEnrichmentUrl: urlOf(loreEnrichmentServer),
      learningUrl: urlOf(knowledgeServer),
      compositionUrl: urlOf(knowledgeServer),
      jobsUrl: urlOf(knowledgeServer),
      agentRegistryUrl: urlOf(knowledgeServer),
      mcpPublicGatewayUrl: urlOf(mcpPublicServer),
    });
    await app.init();
  });

  afterAll(async () => {
    await app.close();
    await Promise.all([
      new Promise((resolve) => authServer.close(resolve)),
      new Promise((resolve) => bookServer.close(resolve)),
      new Promise((resolve) => sharingServer.close(resolve)),
      new Promise((resolve) => catalogServer.close(resolve)),
      new Promise((resolve) => providerRegistryServer.close(resolve)),
      new Promise((resolve) => usageBillingServer.close(resolve)),
      new Promise((resolve) => translationServer.close(resolve)),
      new Promise((resolve) => glossaryServer.close(resolve)),
      new Promise((resolve) => chatServer.close(resolve)),
      new Promise((resolve) => roleplayServer.close(resolve)),
      new Promise((resolve) => videoGenServer.close(resolve)),
      new Promise((resolve) => statisticsServer.close(resolve)),
      new Promise((resolve) => notificationServer.close(resolve)),
      new Promise((resolve) => knowledgeServer.close(resolve)),
      new Promise((resolve) => loreEnrichmentServer.close(resolve)),
      new Promise((resolve) => mcpPublicServer.close(resolve)),
    ]);
  });

  it('routes auth/account paths to auth service', async () => {
    await request(app.getHttpServer()).get('/v1/auth/login').expect(200).expect('auth');
    await request(app.getHttpServer()).get('/v1/account/profile').expect(200).expect('auth');
  });

  it('routes books/sharing/catalog paths to corresponding services', async () => {
    await request(app.getHttpServer()).get('/v1/books').expect(200).expect('books');
    await request(app.getHttpServer()).get('/v1/sharing/books/1').expect(200).expect('sharing');
    await request(app.getHttpServer()).get('/v1/catalog/books').expect(200).expect('catalog');
    await request(app.getHttpServer()).get('/v1/model-registry/providers').expect(200).expect('provider-registry');
    await request(app.getHttpServer()).get('/v1/model-billing/usage-logs').expect(200).expect('usage-billing');
  });

  it('routes /v1/translation/* paths to translation service', async () => {
    await request(app.getHttpServer()).get('/v1/translation/preferences').expect(200).expect('translation');
    await request(app.getHttpServer()).get('/v1/translation/books/book-1/settings').expect(200).expect('translation');
    await request(app.getHttpServer()).get('/v1/translation/jobs/job-1').expect(200).expect('translation');
    await request(app.getHttpServer()).post('/v1/translation/books/book-1/jobs').expect(200).expect('translation');
    await request(app.getHttpServer()).post('/v1/translation/jobs/job-1/cancel').expect(200).expect('translation');
  });

  it('routes /v1/glossary/* paths to glossary service', async () => {
    await request(app.getHttpServer()).get('/v1/glossary/entities').expect(200).expect('glossary');
  });

  it('routes audio endpoints under /v1/books to book service', async () => {
    await request(app.getHttpServer()).get('/v1/books/b1/chapters/c1/audio').expect(200).expect('books');
    await request(app.getHttpServer()).get('/v1/books/b1/chapters/c1/audio/seg-1').expect(200).expect('books');
    await request(app.getHttpServer()).post('/v1/books/b1/chapters/c1/audio/generate').expect(200).expect('books');
    await request(app.getHttpServer()).post('/v1/books/b1/chapters/c1/block-audio').expect(200).expect('books');
    await request(app.getHttpServer()).delete('/v1/books/b1/chapters/c1/audio').expect(200).expect('books');
  });

  it('routes /v1/chat/* paths to chat service', async () => {
    await request(app.getHttpServer()).get('/v1/chat/sessions').expect(200).expect('chat');
  });

  it('routes /v1/roleplay/* paths to roleplay service', async () => {
    await request(app.getHttpServer()).get('/v1/roleplay/scripts').expect(200).expect('roleplay');
    await request(app.getHttpServer()).get('/v1/roleplay/livez').expect(200).expect('roleplay');
  });

  it('routes /v1/lore-enrichment/* paths to lore-enrichment service', async () => {
    await request(app.getHttpServer()).get('/v1/lore-enrichment/jobs').expect(200).expect('lore-enrichment');
  });

  it('routes P5 OAuth authorization-server paths to auth service', async () => {
    // RFC 8414 AS metadata + the /oauth/* endpoints (authorize|token|jwks|register|consent)
    // live in auth-service; external OAuth traffic must still flow through the gateway.
    await request(app.getHttpServer())
      .get('/.well-known/oauth-authorization-server')
      .expect(200)
      .expect('auth');
    await request(app.getHttpServer()).get('/oauth/authorize').expect(200).expect('auth');
    await request(app.getHttpServer()).post('/oauth/token').expect(200).expect('auth');
    await request(app.getHttpServer()).get('/oauth/jwks').expect(200).expect('auth');
    await request(app.getHttpServer()).post('/oauth/register').expect(200).expect('auth');
  });

  it('routes /mcp + RFC 9728 protected-resource metadata to the public MCP edge', async () => {
    // /mcp is the SECOND public entry class (external agents), unversioned; the edge
    // (mcp-public-gateway) also serves the RFC 9728 Protected Resource Metadata.
    await request(app.getHttpServer()).post('/mcp').expect(200).expect('mcp-public');
    await request(app.getHttpServer()).get('/mcp/').expect(200).expect('mcp-public');
    await request(app.getHttpServer())
      .get('/.well-known/oauth-protected-resource')
      .expect(200)
      .expect('mcp-public');
  });

  it('returns 404 for unmatched path', async () => {
    await request(app.getHttpServer()).get('/v1/unknown').expect(404);
    await request(app.getHttpServer()).get('/v1/modelregistry/providers').expect(404);
    await request(app.getHttpServer()).get('/v1/modelbilling/usage-logs').expect(404);
  });

  it('keeps gateway health endpoint stable', async () => {
    await request(app.getHttpServer()).get('/health').expect(200).expect('gateway ok');
  });
});
