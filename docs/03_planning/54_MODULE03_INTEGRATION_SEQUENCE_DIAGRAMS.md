# LoreWeave Module 03 Integration Sequence Diagrams

## Document Metadata

- Document ID: LW-M03-54
- Version: 0.3.0
- Status: Approved
- Owner: Solution Architect + Backend Lead
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Integration sequences for Module 03 BYOK and platform-managed model paths, including metering and billing transitions.

## Change History

| Version | Date       | Change                               | Author    |
| ------- | ---------- | ------------------------------------ | --------- |
| 0.3.0   | 2026-03-21 | Approved by Decision Authority (status governance update) | Assistant |
| 0.2.0   | 2026-03-21 | Added strict provider-gateway enforcement and encrypted interaction-log write/read sequences | Assistant |
| 0.1.0   | 2026-03-21 | Initial Module 03 integration sequences | Assistant |

## 1) BYOK Provider Registration and Health Check

```mermaid
sequenceDiagram
  actor U as User
  participant FE as Frontend
  participant GW as API Gateway
  participant PR as Provider Registry Service
  participant VA as Vault Adapter
  participant PA as Provider Adapter

  U->>FE: Submit provider credential form
  FE->>GW: POST /v1/model-registry/providers
  GW->>PR: Forward request with user claims
  PR->>VA: Store encrypted secret, return secret_ref
  PR->>PA: Execute health check
  PA-->>PR: Reachability/auth result
  PR-->>GW: Credential metadata + health status
  GW-->>FE: Response
  FE-->>U: Show active/invalid state
```

## 2) Strict Provider-Gateway Invocation with Tier->Credits Billing

```mermaid
sequenceDiagram
  actor U as User
  participant FE as Frontend
  participant GW as API Gateway
  participant PG as ProviderGateway
  participant PA as ProviderAdapter
  participant EP as ExternalProvider
  participant UB as Usage Billing Service
  participant ENC as EnvelopeEncryptor
  participant LOG as UsageLogStore

  U->>FE: Invoke model action
  FE->>GW: POST /v1/model-registry/invoke
  GW->>PG: Resolve route and enforce adapter-only path
  PG->>PA: Dispatch invocation
  PA->>EP: Provider API call
  EP-->>PA: Provider response
  PA-->>PG: Response + token telemetry
  PG-->>GW: Invocation result
  GW->>UB: Record usage(request_id, tokens, model_ref)
  UB->>ENC: Encrypt input/output payloads
  ENC-->>UB: Ciphertexts + key_ref
  UB->>LOG: Persist usage + ciphertext + ledger delta
  UB->>UB: Apply billing policy (quota first, then credits)
  UB-->>GW: Usage record + balance delta
  GW-->>FE: Response + usage trace id
  FE-->>U: Show result and updated usage state
```

## 3) Owner Detail Read with Decryption and Audit

```mermaid
sequenceDiagram
  actor U as User
  participant FE as Frontend
  participant GW as API Gateway
  participant UB as Usage Billing Service
  participant AUTH as OwnerAuthz
  participant DEC as DecryptService
  participant AUD as AccessAudit

  U->>FE: Open usage log detail
  FE->>GW: GET /v1/model-billing/usage-logs/{usage_log_id}
  GW->>UB: Fetch metadata + ciphertext
  UB->>AUTH: Verify owner access
  AUTH-->>UB: Allow
  UB->>DEC: Decrypt payloads
  DEC-->>UB: Plaintext input/output
  UB->>AUD: Record detail-view audit
  UB-->>GW: Decrypted detail payload
  GW-->>FE: Detail response
```

## 4) Failure Path - Quota and Credits Exhausted

```mermaid
sequenceDiagram
  participant GW as API Gateway
  participant UB as Usage Billing Service
  participant FE as Frontend

  GW->>UB: Validate billable request
  UB-->>GW: Reject (quota exhausted, credits exhausted)
  GW-->>FE: M03_QUOTA_EXCEEDED or M03_CREDIT_EXHAUSTED
  FE-->>FE: Render actionable billing state
```

## 5) Failure Path - Provider Route Violation

```mermaid
sequenceDiagram
  participant FS as FeatureService
  participant GW as API Gateway
  participant PG as ProviderGateway

  FS->>GW: Runtime request
  GW->>PG: Validate call context
  PG-->>GW: Reject direct/bypass path (M03_PROVIDER_ROUTE_VIOLATION)
  GW-->>FS: Error response
```
