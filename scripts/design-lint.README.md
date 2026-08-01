# design-lint.py — Layer-1 lint for the LLM MMO RPG design corpus

Mechanical cross-doc guard for `docs/03_planning/LLM_MMO_RPG/`. Python 3.10+,
stdlib only, cross-platform (mirrors `ai-provider-gate.py`).

## Why

The 2026-07-26 reconciliation audit (`19_reconciliation_register.md` §14) found
~150 cross-doc defects with one root cause:

> **Documents are locked individually; correctness is a property of the set.**

Per-document review cannot catch set-level drift. This lint mechanizes the
cheapest-to-check classes so they red on contact instead of shipping four times
(the phantom-registration defect literally shipped 4 times).

## Checks

| `--check` value | Finding | What it verifies |
|---|---|---|
| `symbol` | `unregistered-prefix` | Every stable-ID reference `PREFIX-<letter?><n>` (e.g. `RLS-A12`, `EVT-L13`, `DP-Ch18`, `REC-54`) has its `PREFIX` **declared in the id catalog** — the *Prefix* (first) column of `00_foundation/06_id_catalog.md`. A prefix merely *mentioned* in a scope/example cell does not count as declared (no sneak-registration). |
| `link` | `broken-link` | Every relative markdown link `[..](path)` resolves to an existing file/dir. Anchors (`#...`) are ignored; `http(s)://` and `mailto:` are skipped; fenced code blocks and inline code spans are not scanned for links. |
| `registration` | `phantom-registration` | A line claiming registration — `(registered ...)` or `registered YYYY-MM-DD` — names a prefix that actually appears in `_boundaries/01_feature_ownership_matrix.md`. The named prefix is the nearest prefix token before the claim on the same line (fallback: first token on the line, then the doc's filename prefix, e.g. `COMB_003_…` → `COMB`). |
| `count` | *(INFO only)* | v1 does **not** parse "N variants / N tools / count=N" assertions against their lists — it only reports how many such assertions exist (the drift surface). Never affects the exit code. |

Notes on scope:

- The ID regex letter slot accepts any single capital or `Ch` — a superset of
  the originally spec'd `A|D|Q|R|F|I|L|P|T|V|G|Ch`, because `DP-K7`, `EVT-S3`
  and `ITM-C13` are real references the narrow set would miss. Single-letter
  namespaces (`R9`, `C2`, `Q-A4`) are out of scope by design.
- The symbol check scans fenced code blocks too (schemas/tables inside fences
  carry real ID references); the link check does not.

## Usage

```bash
python scripts/design-lint.py                        # full corpus, all checks
python scripts/design-lint.py --path <dir>           # another corpus root
python scripts/design-lint.py --check symbol,link    # subset
python scripts/design-lint.py --max-print 0          # print every finding
python scripts/design-lint.py --allowlist my.json    # alternate allowlist
```

The corpus root must contain `00_foundation/06_id_catalog.md` (symbol check)
and `_boundaries/01_feature_ownership_matrix.md` (registration check); missing
inputs are a config error (exit 2), not a silent pass.

**Exit codes:** `0` clean · `1` findings · `2` usage/config error.

## Allowlisting (symbol check)

Two mechanisms, both requiring a reason:

1. **Corpus-wide** — `scripts/design-lint.allow.json`:
   ```json
   { "prefixes": { "UTF": "UTF-8 — encoding token, not a namespace" } }
   ```
   Seeded with non-namespace tokens (`UTF-8`, `ISO-8601`, `GPT-4`, license
   ids, and the audit-sweep severity numbering `HIGH-n`/`MED-n`/`LOW-n`).
2. **Doc-scoped** — inline pragma, applies only to the containing file:
   ```markdown
   <!-- design-lint: ok prefix XYZ — reason -->
   ```

The right fix for a real namespace is **registering it in the id catalog**,
not allowlisting it here. The allowlist is for tokens that are not IDs at all.

## What v1 deliberately does not do

- No anchor (`#section`) validation, no reference-style `[x]: path` links.
- No count-vs-list parsing (INFO metric only).
- No per-ID existence check (prefix-level only) and no dependency lint
  (V1-item-depends-on-V1+-item) — those are the next layers per §14.

## Pre-commit gate (wired 2026-07-27)

`.githooks/pre-commit` runs the lint on **staged** corpus docs, split by check:

```sh
python scripts/design-lint.py --staged --warn-check symbol
```

| Check | Gate | Why |
|---|---|---|
| `broken-link` | **HARD FAIL** | Mechanical, 0 findings at baseline, effectively no false positives. A dead link is never intentional. |
| `phantom-registration` | **HARD FAIL** | Same, and this exact defect shipped four times — a fabricated "(registered …)" claim is precisely what the gate exists to stop. |
| `unregistered-prefix` | **WARN only** | A genuinely new namespace appears mid-design (`CWC` did, the day this gate landed) and must not block the doc that introduces it. The warning is the reminder to add the catalog row. |

Flags: `--staged` (only staged `.md` under the corpus; deleted paths skipped),
`--warn-check <checks>` (findings print and are counted, but do not fail).
The hook only runs when a corpus `.md` is staged. Emergency bypass:
`git commit --no-verify`.

**Bite-proven at the hook level (2026-07-27)** — four cases, each run through
the real `git commit` path: clean doc → pass · broken link → blocked ·
new prefix `ZZQ-A1` → warned, commit proceeds · phantom
`ZZR-A1 (registered …)` → blocked *while* symbol only warned (proving the
split, and that hard beats soft in the same run).

**The gate was added the moment the baseline hit 1 finding**, deliberately: a
clean baseline is perishable. Without an enforcement point the drift returns
and the gate becomes unaddable — the `jobs-service` pattern (red for six weeks
behind a lint that sat on no commit path).
