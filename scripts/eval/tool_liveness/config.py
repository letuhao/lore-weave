"""TLE harness configuration — endpoints, secrets, DB map (Track D · WS-D2 · P0).

Everything is overridable by env so the harness is portable across a dev docker
stack and CI. Defaults match the local `infra-*` compose stack (host-mapped ports).

Resolve the agent model live (user_default_models is EMPTY for the test account):
  SELECT user_model_id, alias, capability_flags FROM user_models
   WHERE owner_user_id='019d5e3c-...' AND is_active;   (DB loreweave_provider_registry)
Pass the gemma chat+tool_calling UUID as TLE_MODEL_REF. $0 agent spend (local lm_studio).
"""
from __future__ import annotations

import os

# ── Edge / gateway (external entry point; auth path is under test) ────────────
GATEWAY = os.environ.get("TLE_GATEWAY", "http://localhost:3123")
# chat-service direct (host-mapped) — SSE fallback if the gateway proxy chokes.
CHAT_DIRECT = os.environ.get("TLE_CHAT_DIRECT", "http://localhost:8212")
# ai-gateway MCP surface — used only to GENERATE the tool inventory (tools/list).
AI_GATEWAY_MCP = os.environ.get("TLE_AI_GATEWAY_MCP", "http://localhost:8218/mcp")

# ── Test account ──────────────────────────────────────────────────────────────
TEST_EMAIL = os.environ.get("TLE_EMAIL", "claude-test@loreweave.dev")
TEST_PASSWORD = os.environ.get("TLE_PASSWORD", "Claude@Test2026")
USER_ID = os.environ.get("TLE_USER", "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")

# Agent model — REQUIRED (no default-model resolution for this account).
MODEL_REF = os.environ.get("TLE_MODEL_REF", "019ebb72-27a2-72f3-a42d-d2d0e0ded179")

# EMBEDDING model — a fresh knowledge project has none, and kg_build_graph refuses to
# mint its confirm_token without one (F6). Resolve live, per CLAUDE.md's caveat that
# `user_default_models` is EMPTY for the test account:
#   SELECT um.user_model_id FROM user_models um
#   JOIN provider_credentials pc USING (provider_credential_id)
#   WHERE um.owner_user_id='<test-user>' AND um.is_active AND pc.status='active'
#     AND um.capability_flags @> '{"embedding": true}'::jsonb;
EMBEDDING_MODEL_REF = os.environ.get(
    "TLE_EMBEDDING_MODEL_REF", "019e7f71-0271-722f-9c9c-3f049c0b26f4"  # bge-m3 (local, $0)
)

# Secrets (present in the containers; only needed for the self-mint JWT fallback
# + internal-token DB/inventory calls). Never hardcode in committed code.
JWT_SECRET = os.environ.get("TLE_JWT_SECRET", "")
INTERNAL_TOKEN = os.environ.get("TLE_INTERNAL_TOKEN", "dev_internal_token")

# ── Per-domain direct service base URLs (host-mapped) for confirm fallback ────
DOMAIN_BASE = {
    "glossary": os.environ.get("TLE_GLOSSARY", "http://localhost:8211"),
    "book": os.environ.get("TLE_BOOK", "http://localhost:8205"),
    "translation": os.environ.get("TLE_TRANSLATION", "http://localhost:8207"),
    "composition": os.environ.get("TLE_COMPOSITION", "http://localhost:8217"),
    "knowledge": os.environ.get("TLE_KNOWLEDGE", "http://localhost:8216"),
}

# ── Effect-oracle DB map (independent read-back path, per CD3 anti-oracle rule) ─
# The oracle reads the domain's Postgres DIRECTLY — never the domain's read tool —
# so a shared bug in the write tool can't make the check falsely agree.
DOMAIN_DB = {
    "book": os.environ.get("TLE_DB_BOOK", "loreweave_book"),
    "glossary": os.environ.get("TLE_DB_GLOSSARY", "loreweave_glossary"),
    "knowledge": os.environ.get("TLE_DB_KNOWLEDGE", "loreweave_knowledge"),
    "composition": os.environ.get("TLE_DB_COMPOSITION", "loreweave_composition"),
    # a throwaway user's rows also land here (skills / workflows / proposals) and in auth
    "agent_registry": os.environ.get("TLE_DB_AGENT_REGISTRY", "loreweave_agent_registry"),
    "auth": os.environ.get("TLE_DB_AUTH", "loreweave_auth"),
    # a throwaway user's seeded provider credential + model row (so the 6 credential-gated
    # settings_model_* / settings_provider_inventory tools are reachable — a model cannot
    # create a credential itself, OD-S1, so the fixture seeds a KEYLESS one directly).
    "provider_registry": os.environ.get("TLE_DB_PROVIDER_REGISTRY", "loreweave_provider_registry"),
}
# The oracle shells into the postgres container (no host psql / creds needed).
PG_CONTAINER = os.environ.get("TLE_PG_CONTAINER", "infra-postgres-1")
PG_USER = os.environ.get("TLE_PG_USER", "loreweave")

# ── Run tunables ──────────────────────────────────────────────────────────────
TURN_TIMEOUT = int(os.environ.get("TLE_TURN_TIMEOUT", "300"))
STREAM_FORMAT = os.environ.get("TLE_STREAM_FORMAT", "agui")
ALLOW_PAID = os.environ.get("TLE_ALLOW_PAID", "0") == "1"
KEEP_FIXTURES = os.environ.get("TLE_KEEP_FIXTURES", "0") == "1"
