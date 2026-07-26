// AI-Task Standard — composable primitives for one-shot LLM generate surfaces.
// See docs/specs/2026-07-03-ai-task-standard.md. Reuse these instead of hand-rolling
// effort controls, spend-cap inputs, error reads, or propose→confirm boilerplate.
export { EffortSelect } from './EffortSelect';
export {
  type EffortLevel,
  effortLevelFromGenerationParams,
  reasoningEffortForLevel,
} from './effort';
export { SpendCapField, isValidSpend } from './SpendCapField';
export { useAiTask, type AiTask } from './useAiTask';
export { readBackendError } from '@/lib/readBackendError';
