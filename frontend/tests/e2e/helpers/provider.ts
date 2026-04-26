import type { APIRequestContext } from '@playwright/test';

const LM_STUDIO_DISPLAY = 'LM Studio (E2E)';
// NOTE: LM Studio adapter (provider-registry) appends "/v1/chat/completions" itself,
// so endpoint must NOT include "/v1" suffix.
const LM_STUDIO_ENDPOINT = 'http://host.docker.internal:1234';
const QWEN_MODEL_NAME = 'qwen/qwen3.6-35b-a3b';
const QWEN_ALIAS = 'Qwen3 35B (E2E)';

interface Provider {
  provider_credential_id: string;
  provider_kind: string;
  display_name: string;
}

interface UserModel {
  user_model_id: string;
  provider_credential_id: string;
  provider_kind: string;
  provider_model_name: string;
  alias: string | null;
}

function authHeaders(token: string): { Authorization: string } {
  return { Authorization: `Bearer ${token}` };
}

/** Idempotent: returns provider_credential_id for an existing or newly-created LM Studio provider. */
export async function ensureLmStudioProvider(
  request: APIRequestContext,
  token: string,
): Promise<string> {
  const listResp = await request.get('/v1/model-registry/providers', {
    headers: authHeaders(token),
  });
  if (!listResp.ok()) {
    throw new Error(`list providers failed: ${listResp.status()} ${await listResp.text()}`);
  }
  const { items: providers } = (await listResp.json()) as { items: Provider[] };
  const existing = providers.find((p) => p.provider_kind === 'lm_studio');
  if (existing) return existing.provider_credential_id;

  const createResp = await request.post('/v1/model-registry/providers', {
    headers: authHeaders(token),
    data: {
      provider_kind: 'lm_studio',
      display_name: LM_STUDIO_DISPLAY,
      endpoint_base_url: LM_STUDIO_ENDPOINT,
      api_standard: 'lm_studio',
    },
  });
  if (!createResp.ok()) {
    throw new Error(
      `create LM Studio provider failed: ${createResp.status()} ${await createResp.text()}`,
    );
  }
  const created = (await createResp.json()) as Provider;
  return created.provider_credential_id;
}

/** Idempotent: returns user_model_id for the Qwen3 35B model registered against LM Studio. */
export async function ensureLmStudioUserModel(
  request: APIRequestContext,
  token: string,
  providerId: string,
): Promise<string> {
  const listResp = await request.get(
    '/v1/model-registry/user-models?include_inactive=true&provider_kind=lm_studio',
    { headers: authHeaders(token) },
  );
  if (!listResp.ok()) {
    throw new Error(`list user models failed: ${listResp.status()} ${await listResp.text()}`);
  }
  const { items: models } = (await listResp.json()) as { items: UserModel[] };
  const existing = models.find((m) => m.provider_model_name === QWEN_MODEL_NAME);
  if (existing) return existing.user_model_id;

  const createResp = await request.post('/v1/model-registry/user-models', {
    headers: authHeaders(token),
    data: {
      provider_credential_id: providerId,
      provider_model_name: QWEN_MODEL_NAME,
      alias: QWEN_ALIAS,
      context_length: 120_000,
      capability_flags: { _capability: 'chat' },
    },
  });
  if (!createResp.ok()) {
    throw new Error(
      `create user model failed: ${createResp.status()} ${await createResp.text()}`,
    );
  }
  const created = (await createResp.json()) as UserModel;
  return created.user_model_id;
}
