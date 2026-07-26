// Moved to the shared AI-Task Standard location (frontend/src/lib) so every
// AI-task dialog — not just knowledge — reads BE errors the same way. Re-exported
// here so existing `@/features/knowledge/lib/readBackendError` importers are unchanged.
export { readBackendError } from '@/lib/readBackendError';
