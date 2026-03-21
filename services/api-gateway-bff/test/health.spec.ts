import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../src/app.module';
import { configureGatewayApp } from '../src/gateway-setup';

describe('Gateway (e2e)', () => {
  let app: INestApplication;

  beforeAll(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication({ bodyParser: false });
    configureGatewayApp(app, 'http://127.0.0.1:9');
    await app.init();
  });

  afterAll(async () => {
    await app.close();
  });

  it('GET /health returns gateway ok', () => {
    return request(app.getHttpServer()).get('/health').expect(200).expect('gateway ok');
  });
});
