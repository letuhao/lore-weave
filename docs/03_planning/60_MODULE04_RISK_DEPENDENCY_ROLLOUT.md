# LoreWeave Module 04 Risk, Dependency, and Rollout Plan

## Document Metadata

- Document ID: LW-M04-60
- Version: 0.1.0
- Status: Approved
- Owner: SRE + Solution Architect
- Last Updated: 2026-03-22
- Approved By: Decision Authority
- Approved Date: 2026-03-22
- Summary: Risk register, dependency map, and rollout/rollback controls for Module 04 raw translation pipeline.

## Change History

| Version | Date       | Change                              | Author    |
| ------- | ---------- | ----------------------------------- | --------- |
| 0.1.0   | 2026-03-22 | Initial Module 04 risk and rollout doc | Assistant |

## 1) Dependency Map

### Hard Prerequisites

| Dependency | Required state | Risk if unavailable |
| --- | --- | --- |
| M01 auth-service | Operational (JWT issue + verify) | All `/v1/translation/*` endpoints return 401 |
| M03 provider-registry-service | Operational (invoke endpoint) | All translation jobs fail at model invocation step |
| M03 usage-billing-service | Operational | Billing records missing; invoke endpoint may reject requests |
| book-service internal endpoint | `GET /internal/books/{book_id}/chapters/{chapter_id}` available | Chapter text cannot be fetched; all chapters fail |
| api-gateway-bff | `/v1/translation/*` route registered | Translation API unreachable from frontend |

### Soft Dependencies

| Dependency | Impact if missing |
| --- | --- |
| User has configured a provider model in M03 | Job creation returns `TRANSL_NO_MODEL_CONFIGURED` (graceful — not a crash) |
| MinIO (book-service asset storage) | No impact on translation pipeline (chapter text fetched from Postgres via internal endpoint) |

## 2) Risk Register

| ID | Risk | Severity | Likelihood | Mitigation |
| --- | --- | --- | --- | --- |
| R-M04-01 | JWT minting in translation-service uses same `JWT_SECRET` as auth-service — if secret is misconfigured, all invocations fail | High | Low | Verify JWT_SECRET env var at service startup; log warning if missing or too short; fail fast |
| R-M04-02 | M03 invoke endpoint returns 402 (billing exhausted) during job execution | Medium | Medium | Per-chapter billing failure is non-fatal; chapter marked `failed` with `billing_rejected`; job may complete partially |
| R-M04-03 | Provider rate limits cause sequential chapters to pile up | Medium | Medium | Sequential execution avoids burst; per-chapter timeout (60 s) limits stall duration; user can retry job |
| R-M04-04 | FastAPI BackgroundTasks tied to request lifecycle — server restart kills running job | Medium | Low | Startup recovery sweep marks stale `running` jobs as `failed` after 1-hour threshold |
| R-M04-05 | Large chapter text exceeds model context window | Medium | Medium | Provider returns error; chapter marked `failed` with `provider_error`; user must split chapter |
| R-M04-06 | User prompt template missing `{chapter_text}` variable causes empty/wrong translation | High | Low | Frontend validation: reject save if `{chapter_text}` not present in template; backend also validates before job creation |
| R-M04-07 | Translation-service DB (`loreweave_translation`) not created on first boot | Low | Low | DB creation covered by `postgres-db-bootstrap` service and `01-databases.sql` init script; service startup migration will fail loudly if DB missing |
| R-M04-08 | Sequential processing is slow for books with many chapters | Low | High | Acceptable for MVP; parallel execution with concurrency limit planned for future module |
| R-M04-09 | book-service internal API changes break chapter fetch | Medium | Low | Integration test covers chapter fetch path; internal API changes require coordination |

## 3) Rollout Plan

### Rollout sequence

1. Apply DB migration: `loreweave_translation` database and tables created via migration runner on service start.
2. Deploy `translation-service` (Docker Compose `docker compose up translation-service --build`).
3. Apply gateway config: `api-gateway-bff` restart with `TRANSLATION_SERVICE_URL` env set.
4. Verify health: `GET http://localhost:8087/health` returns 200.
5. Smoke test settings endpoints: GET preferences returns defaults.
6. Smoke test job creation with 1 chapter.
7. Full frontend deployment after backend smoke passes.

### Feature flag / dark launch

No feature flag mechanism in MVP. Translation features are gated by:
- User having navigated to `/m04/translation-settings` (no auto-discovery).
- User having configured a model in M03 (otherwise job creation returns error).

### Phased rollout (if needed)

- Phase A: Backend only — smoke test via API before enabling frontend nav links.
- Phase B: Add nav link and book detail link for wider access.

## 4) Rollback Plan

| Scenario | Rollback action |
| --- | --- |
| translation-service fails to start | Remove from docker-compose, gateway loses route (other services unaffected) |
| Gateway misconfiguration | Remove `TRANSLATION_SERVICE_URL` from gateway env; restart gateway |
| DB migration failure | Drop `loreweave_translation` database; fix migration DDL; restart service |
| Frontend pages cause errors | Remove `/m04/translation-settings` and `/books/:bookId/translation` routes from App.tsx; remove nav links; redeploy frontend |

Translation-service is isolated (no other service depends on it in MVP). Rollback affects only M04 features.

## 5) Monitoring and Incident Controls

| Signal | Action |
| --- | --- |
| Job stuck in `running` for > 1 hour | Startup recovery handles on next restart; manually: UPDATE job status via DB admin |
| High rate of `provider_error` on chapters | Check provider health via M03 health endpoint; may indicate provider outage |
| High rate of `billing_rejected` on chapters | Check account balance via M03 `GET /v1/model-billing/account-balance`; user needs to top up credits |
| translation-service unreachable | Restart container; check DB connectivity and JWT_SECRET env |

## 6) Escalation Path

1. **On-call SRE**: service restart and log inspection.
2. **SA + BE lead**: translation-service code issues, provider gateway integration problems.
3. **Decision Authority**: scope changes or rollback decisions affecting the release.
