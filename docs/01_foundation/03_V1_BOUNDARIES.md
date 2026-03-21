# LoreWeave V1 Boundaries (Platform-Core First)

## Document Metadata
- Document ID: LW-03
- Version: 1.1.0
- Status: Draft
- Owner: Product Manager + Solution Architect
- Last Updated: 2026-03-21
- Approved By: Pending
- Approved Date: N/A
- Summary: V1 in-scope/out-of-scope boundaries and non-functional constraints.

## Change History
| Version | Date | Change | Author |
|---|---|---|---|
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

## V1 Non-Functional Constraints

- Deployment target: single-machine Docker Compose
- Architecture: microservices with clear API boundaries
- Source of truth: new services and contracts in `novel_analyzer/`
- Legacy scripts are domain reference only; no runtime coupling

## V1 Exit Criteria

- Users can sign up and log in.
- Authenticated users can create books and manage ownership.
- Books can be shared and browsed based on visibility rules.
- Jobs can be created and tracked through lifecycle states.
- Retrieval endpoint returns evidence-backed results.
- Wiki, QA/extraction, and continuation endpoints are callable in the same platform environment.



