# LoreWeave Service Language Matrix

## Document Metadata

- Document ID: LW-04
- Version: 1.1.0
- Status: Draft
- Owner: Solution Architect
- Last Updated: 2026-03-21
- Approved By: Pending
- Approved Date: N/A
- Summary: Service ownership, language policy, and runtime boundary matrix.

## Change History


| Version | Date       | Change                                                                   | Author    |
| ------- | ---------- | ------------------------------------------------------------------------ | --------- |
| 1.1.0   | 2026-03-21 | Added governance metadata header and migrated to numbered docs structure | Assistant |
| 1.0.0   | 2026-03-21 | Baseline content established before docs reorganization                  | Assistant |


## Goal

Lock language assignment, ownership, and runtime boundaries for each microservice before implementation.

## Language Policy

- Python is mandatory for LangGraph and AI-heavy services.
- Go is the default for high-throughput domain and workflow services.
- TypeScript (NestJS) is the default for gateway/BFF and frontend-facing API composition.

## Service Matrix (V1)


| Service                 | Language   | Framework           | Responsibility                                                | Owner                 |
| ----------------------- | ---------- | ------------------- | ------------------------------------------------------------- | --------------------- |
| `api-gateway-bff`       | TypeScript | NestJS              | API composition, auth guards, request shaping for frontend    | Platform API team     |
| `auth-service`          | Go         | Chi (or Fiber)      | Registration, login, refresh/session, token introspection     | Core platform team    |
| `book-service`          | Go         | Chi (or Fiber)      | Book CRUD, ownership, language metadata, status model         | Core platform team    |
| `sharing-service`       | Go         | Chi (or Fiber)      | Visibility and share policy model (`private/unlisted/public`) | Core platform team    |
| `catalog-service`       | Go         | Chi (or Fiber)      | Browsing and query/filter endpoints for public/allowed books  | Core platform team    |
| `workflow-job-service`  | Go         | Chi (or Fiber)      | Job creation, lifecycle states, retries, history              | Workflow infra team   |
| `orchestrator-service`  | Python     | FastAPI + LangGraph | State machine orchestration for AI workflows                  | AI orchestration team |
| `rag-index-service`     | Python     | FastAPI             | Ingestion, indexing, retrieval, provenance envelopes          | AI knowledge team     |
| `story-wiki-service`    | Python     | FastAPI             | Build wiki pages from indexed artifacts + evidence links      | AI knowledge team     |
| `qa-extraction-service` | Python     | FastAPI             | Grounded QA and structured extraction                         | AI knowledge team     |
| `continuation-service`  | Python     | FastAPI             | Canon-aware continuation generation modes                     | AI creative team      |


## Data and Infra Ownership


| Component                         | Primary Owner       | Consumers                         |
| --------------------------------- | ------------------- | --------------------------------- |
| Postgres                          | Core platform team  | Auth, Book, Sharing, Catalog, Job |
| Redis Streams (or NATS in future) | Workflow infra team | Job, Orchestrator                 |
| MinIO                             | AI knowledge team   | RAG, Orchestrator, Book (assets)  |
| Qdrant                            | AI knowledge team   | RAG, Wiki, QA, Continuation       |
| OpenTelemetry collector stack     | Platform API team   | All services                      |


## Runtime Contracts

- All external client traffic enters through `api-gateway-bff`.
- Internal services expose OpenAPI specs and use explicit versioned contracts.
- AI services never call frontend directly; all user-facing flows return through gateway.
- `workflow-job-service` is the lifecycle authority for job states.

## Exceptions Policy

Any service that violates this matrix needs:

1. architecture review,
2. contract impact assessment,
3. updated matrix proposal approved before merge.


