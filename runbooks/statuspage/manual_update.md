# Runbook — Manual Status Page Update

> **Layer:** L7.L.7 (RAID cycle 37) · **Spec:** SR02 §12AE.2 + problem 10
> **Audience:** SRE on-call · IC
> **Severity profile:** SEV0 / SEV1 (user-visible); SEV2 if customer-noticeable
> **Q-L7L-1 LOCKED:** Statuspage.io V1.

## When to update manually

Normally `statuspage-updater` (L7.L.3) auto-posts from incident events. Update
**manually** when:

1. The updater is degraded or the incident IS the platform (prod-down — but
   the status page is external, Statuspage.io, so it stays reachable).
2. You need wording the pre-approved templates don't cover (two-person rule —
   see `runbooks/incident/comms_under_pressure.md`).
3. A SEV2 became customer-noticeable and you decide to post.

## Where things live

| Thing | Location |
|---|---|
| Status page (public) | Statuspage.io dashboard — URL in 1Password `loreweave-sre/statuspage` |
| Component list | `infra/statuspage/components.yaml` (gateway, auth, world, roleplay, realtime) |
| Banner policy | `infra/statuspage/banner-config.yaml` |
| Comms copy (EN+VI) | `infra/comms/templates/` |
| Page-chrome i18n | `infra/statuspage/templates/{en,vi}.json` |

## Manual procedure

1. **Log in** to Statuspage.io (creds in 1Password; the page is external, so
   this works even during a full prod outage).
2. **Create an incident.** Set the impact per `banner-config.yaml`:
   SEV0 → `critical`, SEV1 → `major`, SEV2 → `minor`.
3. **Select affected components** from the component list. Map the incident's
   affected services to the public component ids.
4. **Paste the pre-approved body.** Use `incident_investigating` first
   (`infra/comms/templates/`). Render the right locale (EN + VI). Do NOT
   freehand — see comms-under-pressure runbook.
5. **Raise the banner** for SEV0/SEV1 (auto in the updater; manual toggle in
   the UI).
6. **Update cadence:** SEV0 every 30 min, SEV1 every 60 min. Use
   `incident_identified` when the cause is known.
7. **On resolve:** post `incident_resolved`, mark the incident resolved, and
   the banner clears (`clear_on_resolve: true`).

## Credentials

The Statuspage.io API key + page id are env-var indirected
(`STATUSPAGE_API_KEY`, `STATUSPAGE_PAGE_ID`) for the updater and NEVER
committed. The UI login is in 1Password, restricted to the SRE rotation.

## Related

- `runbooks/incident/comms_under_pressure.md`
- `runbooks/incident/declaration.md`
- `infra/comms/out_of_band/`

---

> **last_verified:** 1970-01-01
> **verification_method:** stub
