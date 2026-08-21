import type { UserModel, ModelPricing } from '@/features/ai-models/api';
import type { Job } from './types';

/** The two token dimensions used by the jobs cost hint. */
export type TokenModelPricing = Pick<ModelPricing, 'input_per_mtok' | 'output_per_mtok'>;

/** Find the current user-model pricing for a job.
 * Jobs carry the stable user_model ref in params and the resolved provider name
 * in model; the name fallback keeps older jobs useful when params predate model_ref.
 */
export function findJobModelPricing(
  job: Pick<Job, 'model' | 'params'>,
  models: UserModel[] | null | undefined,
): TokenModelPricing | null {
  if (!models?.length) return null;
  const ref = typeof job.params?.model_ref === 'string' ? job.params.model_ref : null;
  const modelName = job.model?.trim().toLocaleLowerCase() ?? null;
  const match =
    (ref ? models.find((m) => m.user_model_id === ref) : undefined) ??
    (modelName
      ? models.find((m) =>
          [m.provider_model_name, m.alias]
            .filter((name): name is string => Boolean(name))
            .some((name) => name.trim().toLocaleLowerCase() === modelName),
        )
      : undefined);
  return match?.pricing ?? null;
}

/** Extrapolate the total job cost from the cost already incurred and progress.
 * Jobs record spend incrementally, so this is the most faithful estimate when a
 * progress total is available. It deliberately never reports less than the
 * already-spent amount. */
export function estimateTotalJobCost(
  costUsd: number | null | undefined,
  progress: { done: number; total?: number } | null | undefined,
): number | null {
  if (costUsd == null || !Number.isFinite(costUsd) || !progress) return null;
  const { done, total } = progress;
  if (
    total == null ||
    !Number.isFinite(done) ||
    !Number.isFinite(total) ||
    done <= 0 ||
    total <= 0
  ) {
    return null;
  }
  return costUsd * Math.max(1, total / done);
}

/** Approximate USD spend at the model's current per-million-token rates.
 * Returns null when neither token count nor either relevant rate is available.
 * This is intentionally a display-only estimate; recorded job.cost_usd remains authoritative.
 */
export function estimateTokenCost(
  tokensIn: number | null | undefined,
  tokensOut: number | null | undefined,
  pricing: TokenModelPricing | null | undefined,
): number | null {
  if (!pricing || (tokensIn == null && tokensOut == null)) return null;
  const inputRate = typeof pricing.input_per_mtok === 'number' && Number.isFinite(pricing.input_per_mtok)
    ? pricing.input_per_mtok
    : null;
  const outputRate = typeof pricing.output_per_mtok === 'number' && Number.isFinite(pricing.output_per_mtok)
    ? pricing.output_per_mtok
    : null;
  if (inputRate == null && outputRate == null) return null;
  const input = tokensIn ?? 0;
  const output = tokensOut ?? 0;
  if (!Number.isFinite(input) || !Number.isFinite(output)) return null;
  return (input * (inputRate ?? 0) + output * (outputRate ?? 0)) / 1_000_000;
}
