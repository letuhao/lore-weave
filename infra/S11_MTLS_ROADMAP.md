# S11 mTLS / JWT-SVID Roadmap (Phase 5)

On-prem ngrok deploy uses **Phase 4** interim controls:

- `INTERNAL_SERVICE_TOKEN` on all `/internal/*` routes
- `contracts/service_acl/matrix.yaml` + `X-Caller-Service` ACL (optional middleware)
- Structured internal RPC audit logs (add per-service as routes harden)

## Phase 5b — JWT-SVID (before AWS ECS prod)

- Issue `Authorization: SVID <jwt>` from platform PKI
- Validate via `sdks/go/svid` (HS256 dev issuer today; AWS PCA later)
- See [S11_service_to_service_auth.md](../docs/03_planning/LLM_MMO_RPG/02_storage/S11_service_to_service_auth.md)

## Phase 5c — mTLS sidecar (V1+30d)

- Envoy sidecar per service; X.509 SVID client certs
- App code unchanged; TLS at sidecar
- **Not required** for on-prem single-port ngrok demo

## Enable ACL middleware (optional)

Set `SERVICE_ACL_ENFORCE=true` on services that import `serviceacl.Middleware` on `/internal/*` route groups.
