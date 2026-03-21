import { INestApplication } from '@nestjs/common';
import { Test, TestingModule } from '@nestjs/testing';
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

  beforeAll(async () => {
    [authServer, bookServer, sharingServer, catalogServer] = await Promise.all([
      startUpstream('auth'),
      startUpstream('books'),
      startUpstream('sharing'),
      startUpstream('catalog'),
    ]);

    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();
    app = moduleFixture.createNestApplication({ bodyParser: false });
    configureGatewayApp(app, {
      authUrl: urlOf(authServer),
      bookUrl: urlOf(bookServer),
      sharingUrl: urlOf(sharingServer),
      catalogUrl: urlOf(catalogServer),
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
  });

  it('returns 404 for unmatched path', async () => {
    await request(app.getHttpServer()).get('/v1/unknown').expect(404);
  });
});
