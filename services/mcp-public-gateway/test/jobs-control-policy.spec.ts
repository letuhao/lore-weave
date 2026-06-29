import {
  isToolAllowed,
  knownTool,
  domainScope,
  TOOL_POLICY,
} from '../src/scope/tool-policy.js';

// P4 slice E / H-N — the agent self-cancel tools `jobs_cancel` / `jobs_pause` are
// Tier-A (write_auto: free + reversible), on the explicit `jobs` domain. They must
// be CLASSIFIED in the allowlist and gated by both the tier scope AND `domain:jobs`
// (never implied by another domain — H-F / H-S).

const JOBS_CONTROL = ['write_auto', domainScope('jobs')];

describe('tool-policy: jobs_cancel / jobs_pause (P4 slice E)', () => {
  it.each(['jobs_cancel', 'jobs_pause'])('classifies %s as write_auto on jobs', (name) => {
    expect(knownTool(name)).toBe(true);
    expect(TOOL_POLICY[name]).toEqual({ tier: 'write_auto', domains: ['jobs'] });
  });

  it.each(['jobs_cancel', 'jobs_pause'])(
    'allows %s for a key holding write_auto + domain:jobs',
    (name) => {
      expect(isToolAllowed(name, JOBS_CONTROL)).toBe(true);
    },
  );

  it.each(['jobs_cancel', 'jobs_pause'])(
    'denies %s when the key lacks the write_auto tier (read-only jobs key)',
    (name) => {
      expect(isToolAllowed(name, ['read', domainScope('jobs')])).toBe(false);
    },
  );

  it.each(['jobs_cancel', 'jobs_pause'])(
    'denies %s when the key lacks domain:jobs (jobs is never implied — H-F/H-S)',
    (name) => {
      // a write_auto key scoped to another domain cannot reach jobs control
      expect(isToolAllowed(name, ['write_auto', domainScope('translation')])).toBe(false);
    },
  );
});
