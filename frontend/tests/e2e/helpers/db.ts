import { execFileSync } from 'node:child_process';

// DB-assert helper for the DB-backed scenarios (telemetry / spoiler / extraction)
// that have no read API. Shells out to `docker exec` against the dev stack's
// Postgres so the e2e can verify backend rows the UI never surfaces. Dev-stack
// only — keyed to the compose container name.
const PG_CONTAINER = process.env.PLAYWRIGHT_PG_CONTAINER ?? 'infra-postgres-1';

/** Run a scalar SQL query against a stack database and return the trimmed text
 * result (psql -tAc). Throws if docker / the container is unavailable. */
export function queryDb(database: string, sql: string): string {
  return execFileSync(
    'docker',
    ['exec', PG_CONTAINER, 'psql', '-U', 'loreweave', '-d', database, '-tAc', sql],
    { encoding: 'utf8' },
  ).trim();
}

export function queryComposition(sql: string): string {
  return queryDb('loreweave_composition', sql);
}

/** True when the dev Postgres container is reachable — gate DB-assert specs on
 * this so they skip (not fail) when the stack isn't up. */
export function dbAvailable(): boolean {
  try {
    queryComposition('SELECT 1');
    return true;
  } catch {
    return false;
  }
}
