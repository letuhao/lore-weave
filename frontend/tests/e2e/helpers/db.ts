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

/** Seed a COMPLETED prior extraction job for a project — puts it in the "has been
 * extracted before" state so worker-ai's auto-drain (_ensure_chapters_pending_jobs)
 * will create a chapters_pending drain for it instead of skipping (`last is None`).
 * Dummy model refs are fine: the auto-drain only COPIES them; we assert that the
 * drain job is CREATED, not that a real extraction runs. user_id is pulled from
 * the project row. */
export function seedPriorExtractionJob(projectId: string): void {
  queryDb(
    'loreweave_knowledge',
    `INSERT INTO extraction_jobs(user_id, project_id, scope, status, llm_model, embedding_model, completed_at)
     SELECT user_id, project_id, 'all', 'complete', 'seed-llm', 'seed-emb', now()
     FROM knowledge_projects WHERE project_id='${projectId}'`,
  );
}

/** Count this project's chapters_pending drain jobs — the signal that the auto-drain
 * engaged (vs the fresh-project skip). */
export function countChaptersPendingJobs(projectId: string): number {
  return Number(queryDb('loreweave_knowledge',
    `SELECT count(*) FROM extraction_jobs WHERE project_id='${projectId}' AND scope='chapters_pending'`));
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
