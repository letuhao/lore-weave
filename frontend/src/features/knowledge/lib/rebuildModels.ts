// KN model-roles — the (llm_model, embedding_model) a rebuild should use.
// Prefers the project's PERSISTED Default LLM (extraction_config.llm_model, set
// in Tune extraction) over the prior job's model, so re-extracting picks up a
// changed default without a bespoke rebuild picker; embedding stays the
// project's current model (changing that is the separate "Change embedding
// model" action). Falls back to the prior job when a value isn't set.

interface RebuildModels {
  llm_model: string;
  embedding_model: string;
}

export function resolveRebuildModels(
  extractionConfig: Record<string, unknown> | undefined,
  embeddingModel: string | null | undefined,
  latest: { llm_model: string; embedding_model: string },
): RebuildModels {
  const persistedDefault = (
    extractionConfig?.llm_model as { model_ref?: string } | undefined
  )?.model_ref;
  return {
    llm_model: persistedDefault || latest.llm_model,
    embedding_model: embeddingModel || latest.embedding_model,
  };
}
