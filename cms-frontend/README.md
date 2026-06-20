# LoreWeave CMS Frontend

A **thin, internal admin CMS** for managing **System-tier glossary standards**
(genres, entity-kinds, attributes). It is a separate app from the main
`frontend/` and exists so platform admins can curate the shared, read-only-to-
users system defaults that every tenant inherits (see the User Boundaries &
Tenancy rules in the repo `CLAUDE.md` — System-tier rows are admin-write only).

It is NOT for regular end users. Regular users clone/override system defaults
into their own per-user/per-book tier in the main app.

## Stack

Vite + React + TypeScript + Tailwind + `@tanstack/react-query`. Talks to the same
`api-gateway-bff` as the main app via the relative `/v1` prefix.

## Run (development)

```bash
npm install
npm run dev
```

Opens on http://localhost:5175. The Vite dev server proxies `/v1` →
`http://localhost:3123` (the host-mapped api-gateway-bff port), so the gateway
stack must be running locally.

## Auth

Sign in on `/login` with an **admin** account. The session token is stored under
the localStorage key `cms_auth` (deliberately distinct from the main app's
`lw_auth`, so both apps can be open at once without clobbering each other).

The admin-JWT exchange / admin-scope enforcement and the real CRUD wiring to the
glossary admin endpoints are built separately; this scaffold ships the login
flow, the protected shell, and placeholder admin panels.

## Build

```bash
npm run build    # tsc --noEmit && vite build
npm run preview  # serve the production build locally
npm test         # vitest run
```

## Production

`Dockerfile` builds the SPA and serves it with nginx; `nginx.conf` proxies
`/v1/` to `http://api-gateway-bff:3000` and falls back to `/index.html` for SPA
routes. The compose service is wired separately.
