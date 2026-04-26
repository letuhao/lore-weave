-- C-LM-STUDIO-FIX follow-up — register LM Studio models for quality eval.
--
-- Run AGAINST the provider-registry-service Postgres database
-- (loreweave_provider_registry) once the LM Studio provider credential
-- is set up and the corresponding model is loaded in LM Studio with
-- the documented context window.
--
-- Discovered during the C19 quality eval cycle:
--   - Coder models (qwen2.5-coder-14b, qwen3-coder-30b) score POORLY on
--     narrative fiction extraction — coder training optimizes for code,
--     not story prose. Use only as a fast smoke test.
--   - Phi-4 ran into context overflow at the 4K default; bump LM Studio
--     load config to ≥16K before using.
--   - **Gemma-4 family is the recommended local-LLM choice** for narrative
--     extraction — strong instruction following + huge context windows.
--
-- Replace the placeholders with your actual values:
--   :owner_user_id          — your auth-service user UUID
--   :provider_credential_id — your LM Studio provider_credentials row UUID
--                             (provider_kind='lm_studio',
--                              endpoint_base_url='http://host.docker.internal:1234')
--
-- After running this script, you can run the C19 quality eval like:
--
--   cd services/knowledge-service
--   PROVIDER_REGISTRY_INTERNAL_URL=http://localhost:8208 \
--   PROVIDER_CLIENT_TIMEOUT_S=600 \
--   KNOWLEDGE_DB_URL=postgresql://loreweave:loreweave_dev@localhost:5432/loreweave_knowledge \
--   GLOSSARY_DB_URL=postgresql://loreweave:loreweave_dev@localhost:5432/loreweave_glossary \
--   INTERNAL_SERVICE_TOKEN=dev_internal_token \
--   JWT_SECRET=loreweave_local_dev_jwt_secret_change_me_32chars \
--   KNOWLEDGE_EVAL_MODEL=<user_model_id from below> \
--   KNOWLEDGE_EVAL_MODEL_SOURCE=user_model \
--   KNOWLEDGE_EVAL_USER_ID=<owner_user_id> \
--   python -m pytest tests/quality/ --run-quality -v -s

INSERT INTO user_models (
  owner_user_id,
  provider_credential_id,
  provider_kind,
  provider_model_name,
  alias,
  is_active,
  context_length,
  capability_flags
) VALUES
  (
    :owner_user_id, :provider_credential_id, 'lm_studio',
    'google/gemma-4-e4b',
    'Gemma-4 E4B (131K context, 4B effective — fast smoke test)',
    true, 131072, '{}'::jsonb
  ),
  (
    :owner_user_id, :provider_credential_id, 'lm_studio',
    'google/gemma-4-26b-a4b',
    'Gemma-4 26B-A4B (64K context — RECOMMENDED narrative model)',
    true, 64000, '{}'::jsonb
  ),
  (
    :owner_user_id, :provider_credential_id, 'lm_studio',
    'microsoft/phi-4',
    'Phi-4 14B (16K context — load LM Studio with ≥16K, default 4K is too small)',
    true, 16000, '{}'::jsonb
  ),
  (
    :owner_user_id, :provider_credential_id, 'lm_studio',
    'qwen/qwen2.5-coder-14b',
    'Qwen2.5 Coder 14B (24K context — coder bias, weak on narrative)',
    true, 24000, '{}'::jsonb
  ),
  (
    :owner_user_id, :provider_credential_id, 'lm_studio',
    'qwen/qwen3.6-35b-a3b',
    'Qwen3.6 35B-A3B (120K context — MoE, active 3B params; user-strongest local model)',
    true, 120000, '{}'::jsonb
  )
ON CONFLICT DO NOTHING
RETURNING user_model_id, provider_model_name, context_length;
