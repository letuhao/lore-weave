import type { APIRequestContext } from '@playwright/test';
import { TEST_USER } from './auth';

/** Login via API and return the access token. */
export async function getAccessToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post('/v1/auth/login', {
    data: { email: TEST_USER.email, password: TEST_USER.password },
  });
  if (!resp.ok()) {
    throw new Error(`API login failed: ${resp.status()} ${await resp.text()}`);
  }
  const body = (await resp.json()) as { access_token: string };
  return body.access_token;
}
