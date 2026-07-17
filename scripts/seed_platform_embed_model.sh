#!/usr/bin/env bash
# Seed the RESERVED PLATFORM-OWNER embedding model (RECONCILE D2) for motif/arc retrieval.
#
# The shared/system "library" tier of motif & arc suggestions is embedded in ONE platform
# vector space so cross-user cosine is comparable (docs/specs/2026-07-17-motif-embedding-
# tenancy-redesign.md). That platform model is a BYOK-as-platform credential — a bge-m3
# (embedding) user_model owned by a reserved platform-owner account — NOT the platform_models
# table (provider-registry /internal/embed only resolves user_models).
#
# This script provisions that account in a DEV provider-registry by COPYING an existing local
# bge-m3 (embedding) credential under fixed, well-known UUIDs so composition's MOTIF_EMBED_*
# env (see infra/docker-compose.yml) resolves the same ids on every dev machine. Idempotent
# (ON CONFLICT DO NOTHING). The AES-GCM secret uses AAD=nil (server.go), so a copied ciphertext
# decrypts fine under the new owner.
#
# PROD does NOT use this — ops registers a real platform account's embed model and points the
# three MOTIF_EMBED_* env vars at it.
#
# Usage:  bash scripts/seed_platform_embed_model.sh [postgres_container]
set -euo pipefail

PG_CONTAINER="${1:-infra-postgres-1}"
DB="loreweave_provider_registry"
PLATFORM_OWNER="00000000-0000-4000-8000-000000000001"
PLATFORM_CRED="00000000-0000-4000-8000-0000000c0001"
PLATFORM_MODEL="00000000-0000-4000-8000-0000000e0001"

echo "Seeding reserved platform embed model ($PLATFORM_MODEL) under owner $PLATFORM_OWNER ..."

docker exec -i "$PG_CONTAINER" psql -U loreweave -d "$DB" -v ON_ERROR_STOP=1 <<SQL
-- Pick any active embedding-capable credential to copy the local bge-m3 endpoint + secret from.
DO \$\$
DECLARE src_model RECORD;
BEGIN
  SELECT um.user_model_id, um.provider_credential_id INTO src_model
  FROM user_models um
  WHERE um.is_active AND um.capability_flags @> '{"embedding": true}'::jsonb
    AND um.owner_user_id <> '$PLATFORM_OWNER'::uuid
  ORDER BY um.created_at
  LIMIT 1;

  IF src_model IS NULL THEN
    RAISE NOTICE 'No embedding-capable user_model found to copy — register a bge-m3 (embedding) model first, then re-run.';
    RETURN;
  END IF;

  INSERT INTO provider_credentials (provider_credential_id, owner_user_id, provider_kind, display_name, endpoint_base_url, secret_ciphertext, secret_key_ref, status, created_at, updated_at, api_standard, max_concurrency)
  SELECT '$PLATFORM_CRED'::uuid, '$PLATFORM_OWNER'::uuid, provider_kind, 'Platform bge-m3 (motif embed)', endpoint_base_url, secret_ciphertext, secret_key_ref, status, now(), now(), api_standard, max_concurrency
  FROM provider_credentials WHERE provider_credential_id = src_model.provider_credential_id
  ON CONFLICT (provider_credential_id) DO NOTHING;

  INSERT INTO user_models (user_model_id, owner_user_id, provider_credential_id, provider_kind, provider_model_name, context_length, alias, is_active, is_favorite, capability_flags, created_at, updated_at, notes, pricing, sort_order)
  SELECT '$PLATFORM_MODEL'::uuid, '$PLATFORM_OWNER'::uuid, '$PLATFORM_CRED'::uuid, provider_kind, provider_model_name, context_length, 'platform-bge-m3', true, false, capability_flags, now(), now(), 'Reserved platform embedding model for shared motif/arc vectors (RECONCILE D2)', pricing, sort_order
  FROM user_models WHERE user_model_id = src_model.user_model_id
  ON CONFLICT (user_model_id) DO NOTHING;
END \$\$;

SELECT um.user_model_id, um.alias, um.capability_flags, pc.provider_kind, pc.endpoint_base_url
FROM user_models um JOIN provider_credentials pc ON pc.provider_credential_id = um.provider_credential_id
WHERE um.owner_user_id = '$PLATFORM_OWNER'::uuid;
SQL

echo "Done. Set (or default) composition's MOTIF_EMBED_OWNER_ID=$PLATFORM_OWNER MOTIF_EMBED_MODEL_REF=$PLATFORM_MODEL MOTIF_EMBED_MODEL_SOURCE=user_model."
