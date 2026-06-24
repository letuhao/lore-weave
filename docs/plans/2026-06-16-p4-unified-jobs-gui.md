# P4 — Unified Jobs GUI (plan)

**Epic:** Unified Background-Job Control Plane (`docs/specs/2026-06-15-unified-job-control-plane.md` §L4).
**Size:** L (FE-only consumer; side-effects=1, owner-scoping enforced server-side).
**PO decisions (2026-06-16):** full generic monitor page (not just a drawer) + dedicated mobile layout.

## Goal

A top-level **/jobs** dashboard: live-list (SSE) every job the user owns across all services,
children grouped under their parent campaign, filter by kind/status, per-row null-safe
status/detail_status/progress, and state-aware cancel/pause/resume gated on each row's
`control_caps`. `kind=campaign` deep-links to the existing `/campaigns/:id` monitor.

## Contract consumed (P2/P3, already shipped + gateway-routed `/v1/jobs/*`)

- `GET /v1/jobs?status=&kind=&parent=&q=&cursor=&limit=` → `{items:[Job], next_cursor}` (keyset).
- `GET /v1/jobs/{service}/{job_id}` → `Job` (404 anti-oracle). PK = `(service, job_id)`.
- `GET /v1/jobs/stream` → SSE; **Bearer in Authorization header (NOT token-in-URL)** → fetch-stream.
- `POST /v1/jobs/{service}/{job_id}/{cancel|pause|resume}` → 200 | 400 | 404 | 409 | 501 | 502.
- `Job` fields: service, job_id, owner_user_id, kind, status, parent_job_id, detail_status,
  progress {done,total}|null, control_caps: ("cancel"|"pause"|"resume")[], title|null,
  error {code,message}|null, created_at, updated_at, child_count|null (list/detail only).
- `control_caps` is **state-aware, recomputed per event** — FE re-reads it every SSE frame.
- JobStatus: pending|running|paused|cancelling|completed|failed|cancelled. TERMINAL = last 3.

## Files (feature `frontend/src/features/jobs/`)

```
types.ts            Job, JobStatus, ControlCap, JobListResponse, JobSseEvent, JobControlAction
api.ts              jobsApi.list/get/control + streamUrl()  (apiJson + apiBase)
hooks/
  useJobsList.ts        useInfiniteQuery, filters {status,kind,parent,q}, keyset cursor
  useJob.ts             useQuery detail (service,jobId)
  useJobControl.ts      cancel/pause/resume mutations → invalidate ['jobs']
  useJobsStream.ts      fetch-stream SSE reader (Bearer), onEvent, reconnect backoff, abort-on-unmount
context/
  JobsStreamProvider.tsx  live overlay Map + THROTTLED invalidate (≤1/1500ms); useJobLive(key)
components/
  JobStatusBadge.tsx   chip, all 7 statuses
  JobControls.tsx      generalized MonitorControls — buttons gated on control_caps[]; confirm-cancel; 409→toast+invalidate
  JobProgress.tsx      null-safe bar + detail_status
  JobRow.tsx           row; campaign→/campaigns/:id else →/jobs/:service/:jobId; expand chevron if child_count>0
  JobChildrenTable.tsx children via useJobsList(parent=jobId)
  JobsFilters.tsx      kind + status selects
  JobsList.tsx         filter bar + rows + grouped children + infinite scroll + live overlay
  JobMonitor.tsx       generic detail body (header, error, progress, detail_status, controls, children)
  mobile/JobsMobile.tsx, mobile/JobMonitorMobile.tsx   mobile card variants
pages/
  JobsPage.tsx         /jobs — useIsMobile swap
  JobDetailPage.tsx    /jobs/:service/:jobId — campaign kind → <Navigate to=/campaigns/:id>
```

Wiring: `App.tsx` (2 routes under RequireAuth+DashboardLayout), `Sidebar.tsx` (nav item,
icon `ListChecks`), i18n `jobs` namespace ×4 + `common.nav.jobs` ×4. Reuse
`@/features/knowledge/hooks/useIsMobile` (pure utility).

## Live-overlay strategy (refetch-storm guard)

`useJobsStream` → on each frame, `JobsStreamProvider` updates `overlay[service:job_id] = event`
(instant per-row re-render with fresh status/progress/control_caps). Separately, a **trailing
throttle** schedules `queryClient.invalidateQueries(['jobs'])` at most once / 1500ms so a
4000-chapter job's event flood can't hammer the list endpoint. New job keys (not in overlay
before) also ride the same throttled invalidate to pull the row in. Overlay split into its
own provider so only consuming rows re-render per frame (FE rule: split context by update freq).

## Build sequence (TDD per unit; one continuous L run, checkpoint at the end)

1. `types.ts` + `api.ts` (+ api test).
2. `useJobsStream` (+ test: SSE frame parse, reconnect, abort) — the riskiest unit first.
3. `JobsStreamProvider` + overlay/throttle (+ test).
4. `useJobsList` / `useJob` / `useJobControl` (+ tests).
5. `JobStatusBadge`, `JobProgress`, `JobControls` (+ tests: caps gating, terminal=none, 409).
6. `JobRow`, `JobChildrenTable`, `JobsFilters`, `JobsList` (+ tests: grouping, filter, deep-link).
7. `JobMonitor` + `JobDetailPage` (+ test: campaign redirect).
8. `mobile/JobsMobile` + `mobile/JobMonitorMobile` (+ tests).
9. `JobsPage` + routing + nav + i18n (4 locales).

## Test plan (vitest + @testing-library/react + react-query)

- Hooks: mock `jobsApi` / `fetch`; assert query keys, invalidation, SSE parsing, reconnect, abort.
- Components: mock hooks/api + `useAuth`; assert caps→button gating, null-safe progress,
  grouping badge, campaign deep-link, filter wiring.
- Coverage of invariants: control_caps gating (not kind-static), terminal→no buttons,
  409→toast, overlay live-update, mobile swap.

## VERIFY / live-smoke

- Primary gate: `npm test` (vitest) green for the new feature.
- **Cross-boundary proof (D-JOBS-P2-SSE-LIVE-SMOKE):** Playwright smoke vs the running stack —
  login (test acct) → open /jobs → see live list → cancel a job → row flips. Verifies the two
  flagged assumptions (campaign job_id==campaign_id; gateway streams SSE unbuffered). If the FE
  image can't be rebuilt at dev time, defer with `D-JOBS-P4-LIVE-SMOKE` + reason.

## Risks / gotchas carried

- Gateway SSE buffering (http-proxy-middleware) could break live updates → live-smoke catches.
- `:5174` is baked prod nginx (memory) — FE changes need a vite-dev run or image rebuild to smoke.
- Owner scoping is server-side; FE must never expose a cross-tenant job (it can't — list is scoped).
