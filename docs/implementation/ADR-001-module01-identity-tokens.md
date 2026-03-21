# ADR-001: Module 01 access and refresh tokens (dev baseline)

## Status

Accepted (implementation baseline)

## Context

Planning doc `12_MODULE01_API_CONTRACT_DRAFT.md` listed open questions on token format and algorithms.

## Decision

- **Access token**: JWT, HS256, signed with `JWT_SECRET` (minimum 32 characters). Claims include `sub` (user UUID), `sid` (session UUID), standard `exp` / `iat`.
- **Refresh token**: Opaque random 32 bytes (base64url), stored as **SHA-256 hash** in `sessions.refresh_token_hash`. TTL from `REFRESH_TOKEN_TTL_SECONDS`.
- **Rotation**: On refresh, previous session row is revoked (`revoked_at`) and a new session row is issued with a new refresh hash (per contract policy draft).

## Consequences

- Simple local/dev operation; **not** suitable for multi-region verification without shared secret rotation story.
- Production should migrate toward **RS256** or token service with key rotation; track as future ADR.

## References

- `docs/03_planning/12_MODULE01_API_CONTRACT_DRAFT.md`
- `services/auth-service/internal/authjwt/jwt.go`
