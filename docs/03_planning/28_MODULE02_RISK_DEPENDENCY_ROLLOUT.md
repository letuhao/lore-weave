# LoreWeave Module 02 Risk, Dependency, and Rollout Plan

## Document Metadata

- Document ID: LW-M02-28
- Version: 1.3.0
- Status: Approved
- Owner: SRE + Solution Architect
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Dependencies, risks, and rollout for Module 02 including MinIO/S3, quota, **chapter drafts/revisions in Postgres**, **recycle bin + future GC**, and roadmap **Gitea**.

## Change History


| Version | Date       | Change                                                | Author    |
| ------- | ---------- | ----------------------------------------------------- | --------- |
| 1.3.0   | 2026-03-21 | Approved by Decision Authority (status governance update) | Assistant |
| 1.0.0   | 2026-03-21 | Initial M02 risk doc                                  | Assistant |
| 1.1.0   | 2026-03-21 | Object storage, quota bypass, malware policy, backup  | Assistant |
| 1.2.0   | 2026-03-21 | Draft/revision risks aligned with `25`              | Assistant |
| 1.3.0   | 2026-03-21 | **Recycle bin / `purge_pending`**, GC job risks, catalog sync (`25` OQ-M02-13–15) | Assistant |


## 1) Dependency Map


| ID      | Dependency                                                         | Blocks                      | Owner | Status  |
| ------- | ------------------------------------------------------------------ | --------------------------- | ----- | ------- |
| M02-D01 | Module 01 tokens stable                                            | All authenticated book APIs | SA    | Active  |
| M02-D02 | Contract freeze (`25` + OpenAPI)                                   | FE lock, QA matrix          | SA    | Active  |
| M02-D03 | DB schema / migrations for books, chapters, policy, quota usage    | Backend persistence         | SA    | Planned |
| M02-D04 | Gateway routes for `/v1/books`, `/v1/sharing`, `/v1/catalog`       | End-to-end client calls     | SA    | Planned |
| M02-D05 | Docker Compose services (book/sharing/catalog or monolith phase)   | Local full stack            | SRE   | Planned |
| M02-D06 | **MinIO or S3-compatible** storage (bucket, creds, network)       | Cover/chapter upload MVP    | SRE   | Planned |
| M02-D07 | **Quota accounting** consistent with object sizes                | Fair use / abuse prevention | SA    | Planned |
| M02-D08 | **Postgres** tables for chapter draft + revision snapshots       | Editor + history MVP        | SA    | Planned |
| M02-D09 | **Garbage collector** (or manual ops) for **`purge_pending`** rows + MinIO delete | Free quota / compliance     | SA    | Roadmap |


## 2) Risk Register


| Risk ID | Description                                                             | Probability | Impact   | Owner    | Mitigation                                                                 |
| ------- | ----------------------------------------------------------------------- | ----------- | -------- | -------- | -------------------------------------------------------------------------- |
| M02-R01 | **Data leak:** private book exposed via catalog or unlisted token guess | Low/Med     | Critical | SA       | Enforce visibility at query layer; rate-limit unlisted resolve; audit logs |
| M02-R02 | **IDOR:** user accesses another owner’s book or chapter by id           | Med         | High     | SA + QAL | Owner checks on every read/write; tests M02-AT-04/06/22                    |
| M02-R03 | **Contract drift** across three OpenAPI files                         | Med         | High     | SA       | Version bump policy; spectral CI on all three paths                        |
| M02-R04 | **Token leakage** of unlisted URL in referrer/logs                      | Med         | Med      | PM + SRE | HTTPS-only prod; short docs for users; avoid logging full path             |
| M02-R05 | **Gateway blast radius** mis-proxy to wrong upstream                    | Med         | High     | SRE      | Route table review; integration tests per path                             |
| M02-R06 | **Migration failure** on existing dev DB                                | Low         | Med      | SRE      | Rollback script; Compose volume reset documented                           |
| M02-R07 | **Object key / URL leak** in API or logs                                | Med         | High     | SA       | Never expose raw keys in public/unlisted; redact URLs in logs              |
| M02-R08 | **Quota bypass** (double upload, race, **trash/purge** not updating bytes) | Med         | Med      | SA + QAL | Transactional quota update; tests M02-AT-17/18/24/45                          |
| M02-R09 | **Malware in uploads** (txt/cover)                                      | Low/Med     | Med      | Sec      | Policy: MVP accept risk vs async scanning; size limits; future AV pipeline |
| M02-R10 | **MinIO/S3 outage or data loss**                                      | Low         | High     | SRE      | Backup/snapshot policy for dev/prod buckets; documented restore drill      |
| M02-R11 | **DB bloat** from full-text revision snapshots                        | Med         | Med      | SA + SRE | Retention cap, prune job, max revision count (`25` OQ)                     |
| M02-R12 | **Draft vs raw mismatch** confuses users or tests                     | Med         | Med      | PM + QAL | Clear UI labels; AT M02-AT-21 vs M02-AT-25                               |
| M02-R13 | **Gitea** (if adopted later): tokens, ACL sync, second backup surface | Low/Med     | High     | SRE      | ADR before enable; isolate network; audit access                           |
| M02-R14 | **Trashed book** still **public** if catalog/sharing projection lags book lifecycle | Low/Med     | Critical | SA       | Integration tests M02-AT-42/43; OQ-M02-15                                 |
| M02-R15 | **GC** deletes wrong rows / partial MinIO delete                         | Low         | High     | SA + SRE | Idempotent GC; txn boundaries (`25` OQ-M02-13); dry-run mode                |
| M02-R16 | Users expect **instant** wipe after “delete”; data retained until GC      | Med         | Low      | PM       | Clear UI copy: recycle bin + “permanent delete” two-step (`26`/`33`)       |


## 3) Rollout Strategy (Planning-Level)

1. **Dev / Compose:** Add services or modules; **provision bucket** and env; run migrations; smoke `27` subset including upload/download.
2. **Internal validation:** Full M02-AT matrix on staging-like env.
3. **Expand:** Enable catalog browse for testers; monitor 404/403 rates on sharing endpoints; monitor **507** quota and storage errors.

## 4) Rollback

- Disable new gateway routes or feature flag (implementation detail).
- Revert migration only if forward fix unsafe; prefer forward fix for data rows.
- Object storage: disabling uploads may be safer than deleting existing objects during incident response.

## 5) Escalation

- Per `06_OPERATING_RACI.md`; visibility or leak suspicion → Decision Authority + SCO.

## 6) References

- `15_MODULE01_RISK_DEPENDENCY_ROLLOUT.md`
- `24_PHASE1_MODULE02_BOOKS_SHARING_EXECUTION_PACK.md`
- `30_MODULE02_MICROSERVICE_SOURCE_STRUCTURE_AMENDMENT.md`
- `04_TECHSTACK_SERVICE_MATRIX.md`
