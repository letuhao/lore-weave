# LoreWeave V1 Boundaries (Platform-Core First)

## Document Metadata
- Document ID: LW-03
- Version: 1.3.0
- Status: Approved
- Owner: Product Manager + Solution Architect
- Last Updated: 2026-03-21
- Approved By: Governance Board
- Approved Date: 2026-03-21
- Summary: V1 in-scope/out-of-scope boundaries and non-functional constraints.

## Change History
| Version | Date | Change | Author |
|---|---|---|---|
| 1.3.0 | 2026-03-21 | Added Module 03 platform-core extension scope for AI provider registry, model catalog, and usage/billing governance baseline | Assistant |
| 1.2.0 | 2026-03-21 | Updated approval metadata to Approved with Governance Board sign-off | Assistant |
| 1.1.0 | 2026-03-21 | Added governance metadata header and migrated to numbered docs structure | Assistant |
| 1.0.0 | 2026-03-21 | Baseline content established before docs reorganization | Assistant |

## Purpose

This document freezes V1 scope for the microservices rewrite so the team can ship a stable platform core before expanding creative capabilities.

## In Scope for V1

### Platform Core
- Authentication and identity
  - registration
  - login
  - token-based auth
- Book management
  - create/list/get books
  - ownership checks
  - chapter/content registration metadata
- Sharing and browsing
  - visibility control (`private`, `unlisted`, `public`)
  - share-link metadata
  - browse public catalog
- AI provider and model control plane
  - user BYOK provider credential registration (OpenAI, Anthropic, Ollama, LM Studio)
  - user model registration and platform-managed model selection
  - usage metering and billing governance (`tier quota + credits overage`)

### Workflow Foundation
- Asynchronous workflow job model
  - queueable jobs
  - job status lifecycle
  - orchestration state transitions
- RAG baseline
  - index text chunks
  - retrieve evidence-backed context

### Knowledge and Assistance (Minimal Functional Baseline)
- Story wiki generation endpoint (from indexed data)
- QA and extraction endpoint with evidence links
- Continuation endpoint with canon safety modes

## Out of Scope for V1

- Rich production UI/UX polish and complete design system
- Advanced recommender ranking models
- Multi-region/cloud autoscaling and full Kubernetes operations
- Full moderation workflow tooling
- Deep analytics and growth experiments
- Enterprise SSO and advanced org administration
- Full invoice/tax pipeline and enterprise billing operations

## V1 Non-Functional Constraints

- Deployment target: single-machine Docker Compose
- Architecture: microservices with clear API boundaries
- Source of truth: new services and contracts in **this monorepo** (repository root: `services/`, `contracts/`, etc.)
- Legacy scripts are domain reference only; no runtime coupling

## V1 Exit Criteria

- Users can sign up and log in.
- Authenticated users can create books and manage ownership.
- Books can be shared and browsed based on visibility rules.
- Users can register providers/models and inspect usage and cost records.
- Jobs can be created and tracked through lifecycle states.
- Retrieval endpoint returns evidence-backed results.
- Wiki, QA/extraction, and continuation endpoints are callable in the same platform environment.





