# Foundation conformance suite (S1)

The conformance runner is the foundation's LTP/xfstests-style battery: a uniform
**verdict contract** that wraps heterogeneous checks — shell lints, Go
`-tags=integration` tests, Rust tests, live probes — into one machine-readable
result. It is **S1** of the foundation runtime test plan
([`docs/specs/2026-06-04-foundation-runtime-test-plan.md`](../../docs/specs/2026-06-04-foundation-runtime-test-plan.md)),
and the contract every later slice (the C/C2/C3 oracles, the fault matrix, the
perf gate) reports into.

## Verdicts

| Verdict  | Meaning | Gate |
|----------|---------|------|
| `pass`   | the case ran and met its assertion | green |
| `fail`   | the case ran and violated its assertion | **red — the only gate-breaking verdict** |
| `notrun` | could not run: a precondition/infra requirement was unmet (no stack, no `DATABASE_URL`), or a harness/setup error | green |
| `skip`   | legitimately not applicable on this stack, or **expunged** (known-broken, tracked) | green |

The cardinal rule: **only `fail` breaks the gate.** This lets the live-stack half
of the suite degrade to `notrun` on a dev box (or a bare CI runner) that lacks
the infra, instead of flapping the build red.

## Run it

```sh
cd tests/conformance
go test ./...                              # the runner's own unit tests
go run ./cmd/conformance -catalog ./catalog
```

Exit code: `0` no failures · `1` ≥1 failure (gate red) · `2` harness error
(catalog/expunge load failed, **zero cases loaded**, or a **dangling expunge
id**). A JSONL record of each run is written to `results/` (gitignored; uploaded
as a CI artifact).

Flags: `-catalog` (catalog tree, default `catalog`), `-repo-root` (where case
commands run, default `../..`), `-results` (JSONL dir, default `results`),
`-run-id` (default: a UTC timestamp), `-allow-empty` (permit a catalog that
loads 0 cases — off by default so a mis-pointed `-catalog` fails loudly instead
of going green), `-case-timeout` (per-case ceiling, default `5m`, `0` disables).

## Add a case

Drop a YAML file under `catalog/generic/` (or a per-service dir):

```yaml
id: my-check                       # unique, stable
description: "what this asserts"
invariant: PRR-32                  # optional I-/PRR-ref for traceability
kind: lint                         # lint | go-test | rust-test | live-probe
command: ["bash", "scripts/my-lint.sh"]   # argv, run from the repo root
requires: ["foundation-stack"]     # preconditions; unmet → notrun
skip_when: ["single-superuser"]    # stack predicates; matched → skip
fail_closed_on_setup_error: false  # exit≥2 → fail (true) vs notrun (false)
```

Unknown YAML keys are rejected (so typos surface). The runner maps a case's
outcome to a verdict by exit code: `0→pass`, `1→fail`, `≥2/launch-error→notrun`
(or `fail` if `fail_closed_on_setup_error`).

**Exit ≥2 is kind-aware.** For `lint`/`live-probe`, exit ≥2 means "couldn't run"
→ `notrun` (lenient, so a missing tool/stack doesn't flap the gate). For
`go-test`/`rust-test`, exit ≥2 is a **build/compile failure** = real breakage, so
those kinds are **fail-closed by default** (exit ≥2 → `fail`). Set
`fail_closed_on_setup_error: true` to force fail-closed on any kind (e.g. a lint
whose exit 2 means a required repo file vanished).

**Predicates** the runner understands today (`internal/runner`):
`requires`: `docker`, `foundation-stack` (the live stack is up = **both** the
foundation Postgres `FOUNDATION_PG_PORT` def 55432 **and** Redis
`FOUNDATION_REDIS_PORT` def 56379 are reachable), `database_url`. `skip_when`:
`single-superuser`, `no-provisioner` (env-gated). An unknown `requires` is
treated as unmet → `notrun` (fail-safe); an unknown `skip_when` does not match.

A per-case `-case-timeout` (default 5m) caps execution: a case that exceeds it →
`notrun` ("timed out"), or `fail` if the case/kind is fail-closed.

## Expunge (known-failures)

`catalog/expunge.yaml` maps a case id to a Deferred-Items ref (xfstests `-E`
semantics). A `fail` on a listed case is downgraded to `skip(expunged)` — it
does **not** break the gate but stays visible in the summary. Every entry MUST
name a ref; the loader rejects an untracked expunge, so there are no silent
skiplists.

## Notes
- **Windows dev:** the runner shells out to `bash scripts/*.sh`; local runs need
  Git Bash or WSL on `PATH`. CI is `ubuntu-latest`.
- **CI live stack:** `conformance-ci.yml` does not boot the foundation-dev stack
  (open item O1), so live-probes report `notrun` there. A green CI run means
  "nothing failed", not "everything ran".
