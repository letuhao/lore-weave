# Perf baselines — INFORMATIONAL ONLY (not a CI gate input)

`bench-baseline.txt` is a raw `go test -bench` capture from **one machine at one
point in time**. It exists so a local developer can eyeball drift on their own
box (`scripts/perf/bench-gate.sh local`).

**It is NOT a CI gate input** (S7 review HIGH-2). A baseline captured on one
machine compared against a different CI runner is a cross-machine diff —
runner-to-runner variance makes that comparison flaky or vacuous. The real CI
regression gate is `bench-gate.sh --ci-ab <base-ref>`, which benches the base
ref **and** HEAD on the **same runner** in one job, so the Mann-Whitney p-value
is meaningful.

Capture provenance of the committed file is in its own `goos:`/`goarch:`/`cpu:`
header lines. Re-capture locally any time with `bench-gate.sh local` after
deleting the file; do not treat a diff against it as authoritative.
