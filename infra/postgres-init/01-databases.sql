-- LoreWeave Database Bootstrap
-- This file runs ONCE when the postgres volume is first created.
-- It creates ALL databases needed by all services.
--
-- To add a new database: add a CREATE DATABASE line below,
-- then delete the postgres volume and restart:
--   docker compose down -v && docker compose up -d postgres
--
-- Or run manually against a running postgres:
--   docker compose exec postgres psql -U loreweave -f /docker-entrypoint-initdb.d/01-databases.sql

-- Auth (default DB, created by POSTGRES_DB env var — but be explicit)
SELECT 'CREATE DATABASE loreweave_auth'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_auth')\gexec

-- Book & Chapter management
SELECT 'CREATE DATABASE loreweave_book'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_book')\gexec

-- Sharing & Visibility
SELECT 'CREATE DATABASE loreweave_sharing'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_sharing')\gexec

-- Scheduler (WS-3.1 — the per-user tick driver's own DB, scheduled_agent_runs)
SELECT 'CREATE DATABASE loreweave_scheduler'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_scheduler')\gexec

-- Public Catalog
SELECT 'CREATE DATABASE loreweave_catalog'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_catalog')\gexec

-- AI Provider Registry (BYOK)
SELECT 'CREATE DATABASE loreweave_provider_registry'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_provider_registry')\gexec

-- Usage & Billing
SELECT 'CREATE DATABASE loreweave_usage_billing'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_usage_billing')\gexec

-- Translation Pipeline
SELECT 'CREATE DATABASE loreweave_translation'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_translation')\gexec

-- Glossary & Lore
SELECT 'CREATE DATABASE loreweave_glossary'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_glossary')\gexec

-- Chat Service
SELECT 'CREATE DATABASE loreweave_chat'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_chat')\gexec

-- Statistics & Leaderboard
SELECT 'CREATE DATABASE loreweave_statistics'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_statistics')\gexec

-- Notifications
SELECT 'CREATE DATABASE loreweave_notification'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_notification')\gexec

-- Lore Enrichment (enriched/"makeup" lore proposals; tables created by the C2 migration)
SELECT 'CREATE DATABASE loreweave_lore_enrichment'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_lore_enrichment')\gexec

-- Learning (Axis-1 correction capture; tables created by learning-service migrate.py)
SELECT 'CREATE DATABASE loreweave_learning'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_learning')\gexec

-- Composition (LOOM co-writer; tables created by composition-service migrate.py M1)
SELECT 'CREATE DATABASE loreweave_composition'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_composition')\gexec

-- Campaign (Auto-Draft Factory saga orchestrator; tables via campaign-service migrate.py)
SELECT 'CREATE DATABASE loreweave_campaign'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_campaign')\gexec

-- Knowledge graph orchestration (tables created by knowledge-service migrate.py)
SELECT 'CREATE DATABASE loreweave_knowledge'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_knowledge')\gexec

-- Event log (worker-infra relay; tables created by worker-infra migrate.go)
SELECT 'CREATE DATABASE loreweave_events'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_events')\gexec

-- Video generation (LLM re-arch Phase 3 M5 — decoupled video_gen_jobs; tables
-- created by video-gen-service migrate.py, mirroring the M1 job-row pattern)
SELECT 'CREATE DATABASE loreweave_video_gen'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_video_gen')\gexec

-- Unified Job Control Plane P2 — jobs-service projection (job_projection +
-- dead_letter_events; tables created by jobs-service migrate.py)
SELECT 'CREATE DATABASE loreweave_jobs'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_jobs')\gexec

-- Roleplay (Rust roleplay-service — scripts + actor-memory + start; tables
-- created by roleplay-service sqlx::migrate! at startup, R1 onward)
SELECT 'CREATE DATABASE loreweave_roleplay'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_roleplay')\gexec

-- Agent Extensibility Registry (plugins/skills/MCP-server registrations; tables
-- created by agent-registry-service migrate.go on startup)
SELECT 'CREATE DATABASE loreweave_agent_registry'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'loreweave_agent_registry')\gexec
