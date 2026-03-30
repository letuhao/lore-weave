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
