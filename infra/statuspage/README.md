# Status Page IaC (L7.L.1)

> **Layer:** L7.L.1 (RAID cycle 37) · **Spec:** SR02 §12AE.2 + problem 10
> **Q-L7L-1 LOCKED:** Statuspage.io V1 (~$29/month, EN+VI). Self-hosted
> (Cachet) is a V2+ option only if cost becomes a concern.

## Why external

The status page is hosted on **Statuspage.io (Atlassian SaaS)** — explicitly
EXTERNAL to the LoreWeave platform infrastructure (SR2 problem 10). When prod
is the incident, the status page must still be reachable. It shares no failure
domain (AWS account, VPC, DNS zone) with the game services. See
`infra/comms/out_of_band/`.

## What lives here

| File | Purpose |
|---|---|
| `main.tf` | Declarative Statuspage.io resources (page, components). Terraform; lint-valid, NOT auto-applied (no live account needed for CI — Q-L7L-1 abstraction). |
| `components.yaml` | Component list matching the service catalog (L7.L.2). Source of truth the updater + Terraform both read. |
| `banner-config.yaml` | Auto-banner policy for SEV0/SEV1 (L7.L.5). |
| `templates/` | i18n comms templates EN + VI (L7.L.4). |

## Credentials

The Statuspage.io API key + page id are NEVER committed. Terraform reads them
from `STATUSPAGE_API_KEY` + `STATUSPAGE_PAGE_ID` env vars (TF_VAR_*). The
`statuspage-updater` service reads the same env vars and fails to start
without them (B6 rule). Terraform here is `terraform validate`-clean but is
applied out-of-band against the real account; CI does not need credentials.

## Apply (out-of-band, by an operator with the account)

```
cd infra/statuspage
terraform init
terraform validate          # CI runs this (no creds needed)
TF_VAR_statuspage_api_key=$STATUSPAGE_API_KEY \
TF_VAR_statuspage_page_id=$STATUSPAGE_PAGE_ID \
  terraform apply           # operator only; requires live account
```
