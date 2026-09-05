import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

/**
 * T48e — every controller is guarded, DERIVED from the tree rather than hand-listed.
 *
 * The KAL write surface is eight destructive entity-lifecycle routes (merge / split / purge /
 * fold / restore / reassign-kind / episodes / resolve-entity), and the census that motivated
 * this file found **zero** tests naming any of them. They were in fact all guarded — the
 * finding is not a live hole, it is that nothing would notice if a new controller arrived
 * without a guard. `InternalTokenGuard`'s own comment calls the misconfig branch
 * defence-in-depth; a route that never reaches a guard has no depth to defend.
 *
 * Hand-listing the controllers here would reproduce the defect one level up (a new file is
 * invisible to a list it is not on), so the scan walks `src/` and the EXEMPTIONS carry a
 * reason and are themselves checked for staleness.
 */

const SRC = join(__dirname, '..', 'src');

/** Controllers that legitimately carry no guard, each with the reason it is safe. */
const EXEMPT: Record<string, string> = {
  [join('health', 'health.controller.ts')]:
    'liveness/readiness are probed by the orchestrator before any token is available, and ' +
    'they expose no tenant data — the guard comment names /health explicitly',
};

function controllers(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...controllers(full));
    else if (name.endsWith('.controller.ts')) out.push(full);
  }
  return out;
}

const FOUND = controllers(SRC);

describe('KAL controller guard coverage (T48e)', () => {
  it('finds the controllers at all — the scan must not pass by finding nothing', () => {
    /* The control arm (rule 3). Every assertion below is satisfied by an empty list, so a
       renamed directory or a changed suffix would turn this whole file green while proving
       nothing. Pinned to the four that exist today: three KAL controllers plus health. */
    expect(FOUND.length).toBeGreaterThanOrEqual(4);
  });

  it.each(FOUND.map((f) => [relative(SRC, f), f] as const))(
    '%s declares a guard (or is exempt with a stated reason)',
    (rel, full) => {
      const src = readFileSync(full, 'utf8');
      const declared = /@UseGuards\(\s*(\w+)/.exec(src);
      if (EXEMPT[rel]) {
        expect(declared).toBeNull();
        return;
      }
      expect(declared).not.toBeNull();
    },
  );

  it('has no stale exemption — an exempted file that no longer exists hides a real gap', () => {
    /* An exemption outliving its file is how a list silently stops describing the tree: the
       name would still be excused if a future controller reused it. */
    const present = new Set(FOUND.map((f) => relative(SRC, f)));
    const stale = Object.keys(EXEMPT).filter((k) => !present.has(k));
    expect(stale).toEqual([]);
  });

  it('the WRITE controller is behind InternalTokenGuard, not the user-facing KalAuthGuard', () => {
    /* Not interchangeable, and the difference is the whole write posture. `KalAuthGuard`
       admits a USER-mode caller holding a book grant; the write surface is service-only
       ("the FE never writes facts directly"). Swapping them would leave every route above
       reachable by any user with edit access to the book — a guard is still declared, so the
       coverage assertion above would stay green. This names the guard. */
    const src = readFileSync(join(SRC, 'kal', 'kal-write.controller.ts'), 'utf8');
    expect(/@UseGuards\(\s*InternalTokenGuard\s*\)/.test(src)).toBe(true);
  });
});
