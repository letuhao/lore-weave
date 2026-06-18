#!/usr/bin/env bash
# verify-cycle-22 — C22 intent-branching onboarding (FE) acceptance gate.
# Per RAID_WORKFLOW.md §13 (exit 0 = pass). FE-only: a first-run "What do you
# want to do?" fork (Write/Build-a-world/Translate/Explore) that routes each
# intent to its tailored surface + the right container, gated by a SERVER-SIDE
# seen-flag (/v1/me/preferences — NOT localStorage-only) with a re-entry door.
# Static asserts + targeted vitest. vitest is run resiliently (bash-spawned
# vitest can hang in this env; PowerShell proves it separately at VERIFY).
set -euo pipefail
CYCLE=22
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FE="$REPO_ROOT/frontend"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-22] FAIL: $1" >&2; audit "verify_cycle_22_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-22] running CI gate"

APP="$FE/src/App.tsx"
HOME="$FE/src/pages/HomePage.tsx"
ROUTES="$FE/src/features/onboarding/lib/intentRoutes.ts"
HOOK="$FE/src/features/onboarding/hooks/useOnboarding.ts"
SCREEN="$FE/src/features/onboarding/components/IntentScreen.tsx"
PAGE="$FE/src/features/onboarding/pages/OnboardingPage.tsx"
TYPES="$FE/src/features/onboarding/types.ts"
SIDEBAR="$FE/src/components/layout/Sidebar.tsx"

# ── 1. onboarding feature folder exists (FE MVC: hook owns logic, view renders) ──
for f in "$ROUTES" "$HOOK" "$SCREEN" "$PAGE"; do
  [ -f "$f" ] || fail "missing $(basename "$f") in features/onboarding/"
done

# ── 2. the four intents route to their tailored surface + right container ──
have "$ROUTES" "'/books'" "intentRoutes: Write must land on the book workspace (/books)"
have "$ROUTES" "'/worlds'" "intentRoutes: Build-a-world must land on the C20/C21 world container (/worlds)"
have "$ROUTES" "/books?intent=translate" "intentRoutes: Translate must route to the translation surface"
have "$ROUTES" "/knowledge/projects" "intentRoutes: Explore must route to the read-only graph/browse surface"
grep -Eq "id: *'write'.*|'write'," "$ROUTES" || fail "intentRoutes missing write intent"
grep -Eq "'world'," "$ROUTES" || fail "intentRoutes missing world intent"
grep -Eq "'translate'," "$ROUTES" || fail "intentRoutes missing translate intent"
grep -Eq "'explore'," "$ROUTES" || fail "intentRoutes missing explore intent"

# ── 3. routes registered in App.tsx (first-run gate + re-entry) ──
have "$APP" "/onboarding" "App.tsx missing /onboarding route"
have "$APP" "/onboarding/new" "App.tsx missing /onboarding/new re-entry route"
have "$APP" "OnboardingPage" "App.tsx missing OnboardingPage element"

# ── 4. first-run gating via the HomePage entry (logged-in → /onboarding gate) ──
have "$HOME" "/onboarding" "HomePage does not gate first-run through /onboarding"

# ── 5. seen-flag persisted SERVER-SIDE via /v1/me/preferences (NOT localStorage-only) ──
have "$HOOK" "syncPrefsToServer" "useOnboarding must write the seen-flag server-side"
have "$HOOK" "loadPrefFromServer" "useOnboarding must read the seen-flag server-side"
have "$HOOK" "ONBOARDING_SEEN_PREF_KEY" "useOnboarding must key off the onboarding seen pref"
have "$TYPES" "hasSeenOnboarding" "the seen-flag pref key must be the /v1/me/preferences 'hasSeenOnboarding' key"
# match actual localStorage API use (localStorage.getItem/setItem), not the word in a comment
grep -Eq "localStorage\.(get|set|remove)Item" "$HOOK" && fail "useOnboarding must NOT use localStorage for the seen-flag (multi-device rule)" || true

# ── 6. routing via EXPLICIT handler, not useEffect-for-events ──
have "$HOOK" "chooseIntent" "useOnboarding missing explicit chooseIntent handler"
have "$SCREEN" "onChoose" "IntentScreen must report the pick via an explicit onChoose callback"
# the view must NOT navigate via a useEffect reaction (match a real call, not a comment)
grep -Eq "useEffect\(" "$SCREEN" && fail "IntentScreen must not use useEffect (explicit handlers only)" || true

# ── 7. re-entry affordance (the door back into the fork) ──
have "$SIDEBAR" "/onboarding/new" "Sidebar missing the re-entry 'start something new' affordance"
have "$PAGE" "forceShow" "OnboardingPage must support the forceShow re-entry mode"

# ── 8. Translate lands on a TAILORED surface (the books page consumes the intent) ──
BOOKS="$FE/src/pages/BooksPage.tsx"
have "$BOOKS" "intent') === 'translate'" "BooksPage must consume ?intent=translate (tailored surface, not a generic shell)"
have "$BOOKS" "translate-intent-hint" "BooksPage missing the translate-intent hint affordance"

# ── 9. ZERO backend drift — only existing /v1/me/preferences allowed ──
grep -RInE "/v1/(worlds|books|knowledge)[^\"']*\b(POST|PUT|DELETE)" "$FE/src/features/onboarding/" 2>/dev/null \
  && fail "onboarding must not mint new BE writes — route only" || true

# ── 9. targeted vitest green ──
cd "$FE"
echo "[verify-cycle-22] vitest (intent routes + screen + gating + parity)"
npx vitest run \
  src/features/onboarding/lib/__tests__/intentRoutes.test.ts \
  src/features/onboarding/components/__tests__/IntentScreen.test.tsx \
  src/features/onboarding/__tests__/OnboardingPage.test.tsx \
  src/i18n/__tests__/onboardingParity.test.ts \
  src/pages/__tests__/BooksPage.translateIntent.test.tsx \
  --reporter=dot --testTimeout=10000 2>&1 | tail -16

audit "verify_cycle_22_passed"
echo "[verify-cycle-22] PASS"
exit 0
