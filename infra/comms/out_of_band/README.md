# Out-of-band comms (L7.D.8)

SR2 problem 10: **when prod is the incident, the comms channel must not depend
on prod.** If the platform is down, a status page hosted on the same infra
cannot tell users the platform is down.

## Principle

Every customer-facing incident comms channel listed here is hosted
**externally** to the LoreWeave platform infrastructure. No component below
shares a failure domain (AWS account, VPC, cluster, DNS zone) with the
production game services.

## Channels

See `channels.yaml` for the authoritative list. V1:

| Channel | Provider | Failure-domain isolation |
|---|---|---|
| Public status page | Statuspage.io (Atlassian-hosted) | Separate SaaS; survives full platform outage (Q-L7L-1) |
| Status-page email/SMS subscribers | Statuspage.io notifications | Same SaaS, still off-platform |
| Founder direct (final escalation) | PagerDuty → phone | Off-platform (Q-L7C-1) |

## What is explicitly NOT a valid out-of-band channel

- A status banner served by `api-gateway-bff` (on-platform; dies with prod)
- An in-app notification (on-platform)
- Anything behind the platform's own DNS/CDN

## Credentials

All provider credentials are env-var indirected and never committed. See
`channels.yaml` for the env var names. Services fail to start if the relevant
key is missing (B6 rule).
