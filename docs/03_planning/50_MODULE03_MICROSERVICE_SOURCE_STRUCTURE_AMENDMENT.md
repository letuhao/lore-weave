# LoreWeave Module 03 Microservice Source Structure Amendment

## Document Metadata

- Document ID: LW-M03-50
- Version: 0.2.0
- Status: Approved
- Owner: Solution Architect
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Source-structure amendment for Module 03 services handling provider credentials, model registry, and usage/billing accounting.

## Change History

| Version | Date       | Change                                     | Author    |
| ------- | ---------- | ------------------------------------------ | --------- |
| 0.2.0   | 2026-03-21 | Approved by Decision Authority (status governance update) | Assistant |
| 0.1.0   | 2026-03-21 | Initial Module 03 source structure amendment | Assistant |

## 1) Purpose

Extend current monorepo structure with Module 03 bounded contexts while preserving contract-first and service ownership conventions.

## 2) Proposed Service Additions

| Service | Responsibility | Suggested language/runtime |
| --- | --- | --- |
| `provider-registry-service` | Credential vault references, provider health checks, user model registry, platform model admin APIs | Go |
| `usage-billing-service` | Usage ingestion, summary aggregation, quota/credit accounting, reconciliation APIs | Go |

Gateway routes remain composed through `api-gateway-bff`.

## 3) Proposed Monorepo Layout

```text
services/
  provider-registry-service/
    cmd/
    internal/
      api/
      domain/
      usecase/
      adapter/
        provider/
        secretvault/
      repository/
  usage-billing-service/
    cmd/
    internal/
      api/
      domain/
      usecase/
      repository/
      aggregator/
contracts/
  api/
    model-registry/v1/
    model-billing/v1/
```

## 4) Data Ownership

- `provider-registry-service` owns:
  - provider credentials metadata,
  - secret vault reference mapping,
  - user model records,
  - platform model catalog records.
- `usage-billing-service` owns:
  - usage log records,
  - billing policy version records,
  - quota/credit ledger snapshots and deltas.

## 5) Internal Integration Contracts

- Registry service exposes internal model metadata lookup endpoint for billing attribution.
- Billing service exposes account-balance read endpoint for runtime policy checks.
- Both services emit audit-friendly events for reconciliation.

## 6) Guardrails

- Secrets are never stored in plaintext in service DB.
- Metering writes must be idempotent per request id.
- Billing computation must include policy version stamp.
