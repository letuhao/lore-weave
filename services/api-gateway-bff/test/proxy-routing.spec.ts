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
  let videoGenServer: http.Server;

  beforeAll(async () => {
    [authServer, bookServer, sharingServer, catalogServer, providerRegistryServer, usageBillingServer, translationServer, glossaryServer, chatServer, videoGenServer] = await Promise.all([
      startUpstream('auth'),
      startUpstream('books'),
      startUpstream('sharing'),
      startUpstream('catalog'),
      startUpstream('provider-registry'),
      startUpstream('usage-billing'),
      startUpstream('translation'),
      startUpstream('glossary'),
      startUpstream('chat'),
      startUpstream('video-gen'),
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
      videoGenUrl: urlOf(videoGenServer),
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
      new Promise((resolve) => videoGenServer.close(resolve)),
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

  it('returns 404 for unmatched path', async () => {
    await request(app.getHttpServer()).get('/v1/unknown').expect(404);
    await request(app.getHttpServer()).get('/v1/modelregistry/providers').expect(404);
    await request(app.getHttpServer()).get('/v1/modelbilling/usage-logs').expect(404);
  });

  it('keeps gateway health endpoint stable', async () => {
    await request(app.getHttpServer()).get('/health').expect(200).expect('gateway ok');
  });
});
