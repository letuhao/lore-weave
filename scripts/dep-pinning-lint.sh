#!/usr/bin/env bash
# L1.K.8 dep-pinning-lint.sh — SR10 I18
#
# Verifies dependency declarations are hash-pinned where the ecosystem
# supports it:
#   - Go: go.sum must exist for every go.mod that declares external requires
#   - Rust: Cargo.lock must exist at workspace root
#   - Python: every declared dependency carries a version constraint
#   - Docker: FROM lines MUST use digest pin (`image@sha256:...`) — warn if tag-only
#
# Exit 0 = clean; 1 = violations; 2 = misuse / selftest failure / the scan
# reached nothing.
#
# RED-ABILITY PROOF (`GATE-TEETH`, 2026-08-12), and a scope fix that dwarfs it.
#
# ⚠️ **THIS GATE WAS SCANNING 89% FOREIGN TREES.** Measured: 675 `go.mod` of
# which **600** were under `.claude/worktrees/` (agent scratch copies of this
# repo); 324 `Dockerfile` of which **288** were; 153 `requirements*.txt` of
# which **136** were in worktrees, `site-packages` or `vendor`. It excluded
# `node_modules` and `.venv` and nothing else, so it was judging third-party
# virtualenv packages and duplicate checkouts by this repo's convention — 1440
# dependency lines "judged", most of them not ours. Two costs: latency (the
# exact class `admin-command-registry-lint` already paid, up to a 900s timeout
# under `--run-all`), and a false finding waiting to happen the day a vendored
# package ships a bare `requests`. Real counts after pruning: 75 / 17 / 3 / 36.
#
# The predicates are extracted so `--selftest` drives them, and each arm now
# carries a REACH FLOOR — including one on dependency LINES judged, because the
# constraint rule is the load-bearing arm and a parse that silently yields zero
# lines is a pass over nothing.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"

# Trees that are not this repo's dependency declarations. `.claude` holds agent
# worktrees — full copies of this checkout — and `site-packages`/`vendor` hold
# other people's code. A rule about OUR pinning has no business reading either.
#
# **`-prune`, not `-not -path`, and the difference is the whole runtime.**
# `-not -path '*/target/*'` filters the RESULTS; find still DESCENDS into every
# pruned directory, so each of the four scans below walked two complete Rust
# build trees under `.claude/worktrees/*/target/`. Measured: 51-76s for a gate
# whose real subject is 131 files. `-prune` stops the traversal.
_PRUNED=(-path '*/node_modules' -o -path '*/.venv' -o -path '*/.claude'
         -o -path '*/site-packages' -o -path '*/vendor' -o -path '*/target'
         -o -path '*/.git' -o -path '*/dist' -o -path '*/__pycache__')

find_repo() {  # $1 = -name pattern
  find "$repo_root" \( "${_PRUNED[@]}" \) -prune -o -name "$1" -print 2>/dev/null
}

# --- PREDICATES, extracted so cases can drive them --------------------------

# Does this dependency spec carry a version constraint?
has_constraint() {
  [[ "$1" =~ [=\<\>~!] ]]
}

# Is this line one the constraint rule should judge at all?
is_dep_line() {
  local dep="$1"
  [[ -n "$dep" && "$dep" != \#* && "$dep" != -* ]]
}

# Does this go.mod declare an external require (single-line or block form)?
go_declares_external() {
  local mod="$1"
  grep -qE '^require[[:space:]]+[a-z]+\.[a-z]' "$mod" 2>/dev/null && return 0
  awk '/^require[[:space:]]+\($/,/^\)$/' "$mod" 2>/dev/null | grep -qE '^\s+[a-z]+\.[a-z]' && return 0
  return 1
}

# Does this FILE carry a FROM with no digest pin?
#
# **Takes a path, not a line, and that is deliberate.** A line-predicate forced
# the scan to read every Dockerfile line-by-line in bash, which is far slower
# than one `grep -q` per file — and the selftest would then be exercising a
# predicate the real path no longer used the same way. One implementation, used
# by both; the cases below write temp files rather than pass strings.
from_tag_pinned() {
  grep -qE '^FROM[[:space:]]+[^@]*$' "$1"
}

run_lint() {
  local violations=0 n_go=0 n_req=0 n_py=0 n_docker=0 n_deplines=0
  local mod dir req py dockerfile dep

  # Go: every go.mod with external `require` blocks needs a go.sum sibling.
  # A module with NO external deps doesn't need one — `go mod tidy` does not
  # create it in that case.
  while IFS= read -r mod; do
    n_go=$((n_go + 1))
    dir=$(dirname "$mod")
    [[ -f "$dir/go.sum" ]] && continue
    if go_declares_external "$mod"; then
      echo "[dep-pinning] FAIL — $mod declares external requires but has no go.sum sibling"
      violations=$((violations + 1))
    fi
  done < <(find_repo go.mod)

  # Rust workspace root must have Cargo.lock
  if [[ -f "$repo_root/Cargo.toml" ]] && ! [[ -f "$repo_root/Cargo.lock" ]]; then
    echo "[dep-pinning] FAIL — workspace Cargo.toml without Cargo.lock"
    violations=$((violations + 1))
  fi

  # Python — lockfiles are not this repo's convention and never have been:
  # services pin with floor constraints in requirements.txt. The arm guards the
  # convention that IS load-bearing — every declared dependency carries a
  # version constraint — which is green today and genuinely red-able.
  while IFS= read -r req; do
    n_req=$((n_req + 1))
    while IFS= read -r dep; do
      is_dep_line "$dep" || continue
      n_deplines=$((n_deplines + 1))
      if ! has_constraint "$dep"; then
        echo "[dep-pinning] FAIL — $req declares '$dep' with no version constraint"
        violations=$((violations + 1))
      fi
    done < <(sed 's/[[:space:]]*#.*//' "$req")
  done < <(find_repo 'requirements*.txt')

  # Same rule for the `dependencies = [...]` block of each pyproject.toml.
  while IFS= read -r py; do
    n_py=$((n_py + 1))
    while IFS= read -r dep; do
      n_deplines=$((n_deplines + 1))
      if ! has_constraint "$dep"; then
        echo "[dep-pinning] FAIL — $py declares '$dep' with no version constraint"
        violations=$((violations + 1))
      fi
    done < <(awk '/^dependencies[[:space:]]*=[[:space:]]*\[/{f=1;next} f&&/^\]/{f=0} f' "$py" \
               | sed 's/[[:space:]]*#.*//' | tr -d ' ",' | grep -v '^$')
  done < <(find_repo pyproject.toml)

  # Docker: warn-only on tag-pinned FROM (no fail; many base images don't ship digest).
  #
  # **Reported as a RATIO, not as one line per file.** Measured 2026-08-12:
  # **36 of 36** Dockerfiles are tag-pinned and **zero** digest-pinned FROMs
  # exist anywhere in the tree. A warn that fires on 100% of its subjects has no
  # discriminating power — it was 36 identical lines on every CI run, which is
  # how a gate teaches people to skip its output. The ratio still moves the day
  # someone digest-pins one, and that is the only signal this arm ever had.
  local n_tagged=0
  while IFS= read -r dockerfile; do
    n_docker=$((n_docker + 1))
    if from_tag_pinned "$dockerfile"; then
      n_tagged=$((n_tagged + 1))
    fi
  done < <(find_repo Dockerfile)
  if [[ $n_tagged -gt 0 ]]; then
    echo "[dep-pinning] WARN — $n_tagged of $n_docker Dockerfile(s) use a tag-pinned FROM"
    echo "              (consider digest pins; tracked as GT-DOCKER-WARN-100PCT while the"
    echo "              ratio stays at 100%, where a per-file warning is noise not signal)"
  fi

  # Violations outrank the floors: a gate that found something demonstrably had
  # a subject, and reporting a real finding as a misuse code is the ordering
  # mistake `language-rule-lint` shipped for ten minutes.
  if [[ $violations -gt 0 ]]; then
    echo "[dep-pinning] FAIL — $violations unpinned dep declaration(s) (SR10 I18)"
    exit 1
  fi

  # REACH FLOORS. Every arm walks a `find`; a typo'd prune or a moved tree makes
  # any of them match nothing, and "no violations over zero files" prints PASS
  # with exit 0 — indistinguishable from compliance (`BDR-82`). The dep-LINE
  # floor is the load-bearing one: the constraint rule is this gate's only
  # failing arm, and its subject is lines, not files.
  local why=""
  [[ $n_go -lt 1 ]]       && why="$why no go.mod;"
  [[ $n_req -lt 1 ]]      && why="$why no requirements*.txt;"
  [[ $n_py -lt 1 ]]       && why="$why no pyproject.toml;"
  [[ $n_docker -lt 1 ]]   && why="$why no Dockerfile;"
  [[ $n_deplines -lt 1 ]] && why="$why ZERO dependency lines judged;"
  if [[ -n "$why" ]]; then
    echo "[dep-pinning] FAIL — the scan reached nothing on at least one arm:$why"
    echo "              a walk that reaches nothing is indistinguishable from a clean tree"
    exit 2
  fi

  echo "[dep-pinning] PASS — $n_go go.mod, $n_req requirements file(s), $n_py pyproject(s),"
  echo "              $n_docker Dockerfile(s); $n_deplines dependency line(s) checked for a constraint"
  exit 0
}

selftest() {
  # has_constraint — every operator the rule claims, and the negative that is
  # the whole point of the arm.
  local ok
  for ok in 'requests>=2.0' 'flask==1.1.4' 'x<3' 'y~=1.2' 'z!=0.9' 'a<=2,>=1'; do
    has_constraint "$ok" || { echo "[dep-pinning] SELFTEST FAIL — constrained dep rejected: $ok"; exit 2; }
  done
  if has_constraint 'requests'; then
    echo "[dep-pinning] SELFTEST FAIL — a BARE dependency passed the constraint rule (vacuous)"; exit 2
  fi
  if has_constraint 'uvicorn[standard]'; then
    echo "[dep-pinning] SELFTEST FAIL — an extras-only spec with no version passed"; exit 2
  fi

  # is_dep_line — the filter that decides what the rule even looks at. Widen it
  # and pip flags get judged; narrow it and real deps go unread.
  is_dep_line 'requests>=2.0' || { echo "[dep-pinning] SELFTEST FAIL — a real dep line was skipped"; exit 2; }
  if is_dep_line '# a comment'; then echo "[dep-pinning] SELFTEST FAIL — a comment is being judged"; exit 2; fi
  if is_dep_line '-r base.txt';  then echo "[dep-pinning] SELFTEST FAIL — a pip flag is being judged"; exit 2; fi
  if is_dep_line '';             then echo "[dep-pinning] SELFTEST FAIL — a blank line is being judged"; exit 2; fi

  # go_declares_external — both forms, and a module with none.
  local d; d="$(mktemp -d)"; trap 'rm -rf "$d"' RETURN
  printf 'module x\n\nrequire github.com/pkg/errors v0.9.1\n' > "$d/single"
  printf 'module x\n\nrequire (\n\tgithub.com/pkg/errors v0.9.1\n)\n' > "$d/block"
  printf 'module x\n\ngo 1.22\n' > "$d/none"
  go_declares_external "$d/single" || { echo "[dep-pinning] SELFTEST FAIL — single-line require not seen"; exit 2; }
  go_declares_external "$d/block"  || { echo "[dep-pinning] SELFTEST FAIL — require BLOCK not seen"; exit 2; }
  if go_declares_external "$d/none"; then
    echo "[dep-pinning] SELFTEST FAIL — a module with no external requires was flagged (cry-wolf:"
    echo "              go mod tidy does not create a go.sum for it)"; exit 2
  fi

  # from_tag_pinned — the warn arm, both directions, through real files because
  # that is what the scan passes it.
  printf 'FROM python:3.12-slim\nRUN echo hi\n' > "$d/tagged"
  printf 'FROM python@sha256:abc123\nRUN echo hi\n' > "$d/digest"
  from_tag_pinned "$d/tagged" || { echo "[dep-pinning] SELFTEST FAIL — a tag-pinned FROM not detected"; exit 2; }
  if from_tag_pinned "$d/digest"; then
    echo "[dep-pinning] SELFTEST FAIL — a DIGEST-pinned FROM was reported (cry-wolf)"; exit 2
  fi

  echo "[dep-pinning] SELFTEST PASS — 6 constraint operators accepted and a bare dep refused;"
  echo "              the line filter skips comments/flags/blanks and keeps real deps; both"
  echo "              go.mod require forms detected and a require-less module left alone; and"
  echo "              a tag-pinned FROM flagged while a digest-pinned one is not"
}

case "${1:-}" in
  --selftest) selftest ;;
  --lint)     run_lint ;;
  "")         selftest; run_lint ;;
  *)          echo "usage: $0 [--selftest | --lint]"; exit 2 ;;
esac
