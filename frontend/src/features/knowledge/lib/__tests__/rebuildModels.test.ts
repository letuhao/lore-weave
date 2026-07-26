import { describe, it, expect } from 'vitest';
import { resolveRebuildModels } from '../rebuildModels';

const latest = { llm_model: 'prior-job-llm', embedding_model: 'prior-job-embed' };

describe('resolveRebuildModels (KN model-roles — rebuild picks up a changed default)', () => {
  it('prefers the persisted Default LLM (extraction_config.llm_model) over the prior job', () => {
    const got = resolveRebuildModels(
      { llm_model: { model_ref: 'new-default-llm' } },
      'project-embed',
      latest,
    );
    expect(got.llm_model).toBe('new-default-llm');
    expect(got.embedding_model).toBe('project-embed');
  });

  it('falls back to the prior job model when no default LLM is persisted', () => {
    expect(resolveRebuildModels({}, 'project-embed', latest).llm_model).toBe('prior-job-llm');
    expect(resolveRebuildModels(undefined, null, latest)).toEqual(latest);
  });

  it('a Default-LLM object with no model_ref falls back to the prior job', () => {
    expect(
      resolveRebuildModels({ llm_model: { model_source: 'user_model' } }, undefined, latest).llm_model,
    ).toBe('prior-job-llm');
  });

  it('the project embedding model wins over the prior job embedding', () => {
    expect(resolveRebuildModels({}, 'current-embed', latest).embedding_model).toBe('current-embed');
  });
});
