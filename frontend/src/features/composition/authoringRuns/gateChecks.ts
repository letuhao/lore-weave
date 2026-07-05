// #20_agent_mode.md §2/§4 — the "4 gate checks" the mockup renders. The REAL
// backend gate() (authoring_run_service.py:650-711) is all-or-nothing: it
// raises on the FIRST failing rule rather than returning a structured 4-check
// report, and does not expose an "account budget limit" concept the mockup's
// 3rd check implied (that check is honestly relabeled below to what the
// backend ACTUALLY validates: budget_usd > 0 — not a hardcoded always-pass,
// derived from real caller-entered/persisted data + the plan's real fetched
// status + the book's real chapter-id set).
export interface GateCheckItem {
  id: 'plan' | 'scope' | 'budget' | 'allowlist';
  passed: boolean;
  detail: string;
}

export interface GateCheckInput {
  /** Status of the SELECTED plan run, or null when nothing is picked / not loaded yet. */
  planStatus: string | null;
  /** The run's ordered chapter-id scope. */
  scopeIds: string[];
  /** The book's real active chapter ids, or null while still loading (scope
   * membership is then treated as unverified, not silently passed). */
  bookChapterIds: Set<string> | null;
  budgetUsd: number;
  toolAllowlist: string[];
}

const APPROVED_PLAN_STATUSES = new Set(['validated', 'compiled']);

export function computeGateChecks(input: GateCheckInput): GateCheckItem[] {
  const planOk = !!input.planStatus && APPROVED_PLAN_STATUSES.has(input.planStatus);
  const scopeNonEmpty = input.scopeIds.length > 0;
  const scopeKnownValid =
    input.bookChapterIds === null ? null : input.scopeIds.every((id) => input.bookChapterIds!.has(id));
  const scopeOk = scopeNonEmpty && scopeKnownValid !== false;
  const budgetOk = input.budgetUsd > 0;
  const allowlistOk = input.toolAllowlist.length > 0 && input.toolAllowlist.every((t) => t.trim().length > 0);

  return [
    {
      id: 'plan',
      passed: planOk,
      detail: input.planStatus
        ? `plan_run_id → status=${input.planStatus}`
        : 'no plan selected',
    },
    {
      id: 'scope',
      passed: scopeOk,
      detail: !scopeNonEmpty
        ? 'scope is empty'
        : scopeKnownValid === null
          ? `${input.scopeIds.length} chapter(s) — verifying against the book…`
          : scopeKnownValid
            ? `${input.scopeIds.length} chapter(s), all in this book`
            : 'one or more chapters are not in this book',
    },
    {
      id: 'budget',
      passed: budgetOk,
      detail: budgetOk ? `$${input.budgetUsd.toFixed(2)} declared` : 'budget must be greater than $0',
    },
    {
      id: 'allowlist',
      passed: allowlistOk,
      detail: allowlistOk ? `${input.toolAllowlist.length} tool(s)` : 'tool allowlist must be non-empty',
    },
  ];
}

export function allGateChecksPass(items: GateCheckItem[]): boolean {
  return items.every((i) => i.passed);
}
