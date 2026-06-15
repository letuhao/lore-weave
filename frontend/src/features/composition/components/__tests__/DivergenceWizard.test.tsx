import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const deriveWorkMock = vi.fn();
vi.mock('../../api', () => ({
  compositionApi: { deriveWork: (...a: unknown[]) => deriveWorkMock(...a) },
}));
// Step bodies fetch chapters/entities — stub the data layers so the view renders.
const listEntitiesMock = vi.fn().mockResolvedValue({ entities: [], total: 0 });
vi.mock('../../../books/api', () => ({
  booksApi: { listChapters: vi.fn().mockResolvedValue({ items: [], total: 0 }) },
}));
vi.mock('../../../knowledge/api', () => ({
  knowledgeApi: { listEntities: (...a: unknown[]) => listEntitiesMock(...a) },
}));

import { DivergenceWizard } from '../DivergenceWizard';
import type { Work } from '../../types';

const sourceWork: Work = {
  project_id: 'src-proj', user_id: 'u', book_id: 'book-1',
  active_template_id: null, status: 'active', settings: {}, version: 1,
};

function renderWizard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(
    <Wrapper>
      <DivergenceWizard open onOpenChange={() => {}} sourceWork={sourceWork} token="tok" />
    </Wrapper>,
  );
}

beforeEach(() => {
  deriveWorkMock.mockReset();
  listEntitiesMock.mockReset();
  listEntitiesMock.mockResolvedValue({ entities: [], total: 0 });
});

// C24-fix (id-space): an anchored (canonical) entity carries a glossary_entity_id;
// the override the wizard submits MUST be keyed on that glossary anchor (the id the
// packer's present-lens keys on), NOT the knowledge node id (`entity.id`). An
// unanchored (discovered) entity has no anchor → overriding it is disallowed with a
// hint (we never silently write the knowledge node id).
function entity(over: Partial<Record<string, unknown>>) {
  return {
    id: 'know-node', user_id: 'u', project_id: 'src-proj', name: 'Ent',
    canonical_name: 'Ent', kind: 'character', aliases: [], canonical_version: 1,
    source_types: [], confidence: 1, glossary_entity_id: null, anchor_score: 0,
    archived_at: null, status: 'discovered', evidence_count: 0, mention_count: 5,
    user_edited: false, version: 1, created_at: null, updated_at: null, ...over,
  };
}

describe('DivergenceWizard — override id-space (C24 fix)', () => {
  it('an anchored entity submits its GLOSSARY anchor id as target_entity_id (not the knowledge node id)', async () => {
    listEntitiesMock.mockResolvedValue({
      entities: [entity({
        id: 'know-node-zrc', name: '张若尘', glossary_entity_id: 'gloss-anchor-zrc',
        status: 'canonical', anchor_score: 1,
      })],
      total: 1,
    });
    deriveWorkMock.mockResolvedValue({ project_id: 'deriv', source_work_id: 'sw' });
    renderWizard();
    fireEvent.click(screen.getByTestId('divergence-next')); // →2
    fireEvent.click(screen.getByTestId('divergence-next')); // →3
    // the row is keyed by the GLOSSARY anchor id, and its input writes the anchor.
    const input = await screen.findByTestId('divergence-override-input-gloss-anchor-zrc');
    fireEvent.change(input, { target: { value: 'now a woman (genderbend)' } });
    fireEvent.click(screen.getByTestId('divergence-next')); // →4
    fireEvent.change(screen.getByTestId('divergence-name'), { target: { value: 'Genderbend AU' } });
    fireEvent.click(screen.getByTestId('divergence-submit'));
    await waitFor(() => expect(deriveWorkMock).toHaveBeenCalled());
    const body = deriveWorkMock.mock.calls[0][1];
    expect(body.entity_overrides).toEqual([
      { target_entity_id: 'gloss-anchor-zrc', overridden_fields: { description: 'now a woman (genderbend)' } },
    ]);
    // the knowledge node id must NOT leak into the override target.
    expect(body.entity_overrides[0].target_entity_id).not.toBe('know-node-zrc');
  });

  it('an unanchored (discovered) entity cannot be overridden — the input is disabled with a hint', async () => {
    listEntitiesMock.mockResolvedValue({
      entities: [entity({
        id: 'know-node-disc', name: 'Nobody', glossary_entity_id: null, status: 'discovered',
      })],
      total: 1,
    });
    renderWizard();
    fireEvent.click(screen.getByTestId('divergence-next')); // →2
    fireEvent.click(screen.getByTestId('divergence-next')); // →3
    // No anchor → no override input keyed on the knowledge id, and a hint is shown.
    expect(screen.queryByTestId('divergence-override-input-know-node-disc')).toBeNull();
    expect(await screen.findByTestId('divergence-unanchored-hint-know-node-disc')).toBeTruthy();
  });
});

describe('DivergenceWizard (DPS1 — 4-step view)', () => {
  it('renders the 4-step rail and all 4 step bodies stay MOUNTED (no conditional unmount)', () => {
    renderWizard();
    expect(screen.getByTestId('divergence-rail')).toBeTruthy();
    // All four step bodies are present in the DOM even though only step 1 is visible
    // (internal branching via CSS hidden — NOT a ternary that unmounts the others).
    expect(screen.getByTestId('divergence-step-1')).toBeTruthy();
    expect(screen.getByTestId('divergence-step-2')).toBeTruthy();
    expect(screen.getByTestId('divergence-step-3')).toBeTruthy();
    expect(screen.getByTestId('divergence-step-4')).toBeTruthy();
  });

  it('Next advances through the steps to the Spawn submit', () => {
    renderWizard();
    expect(screen.getByTestId('divergence-next')).toBeTruthy();
    fireEvent.click(screen.getByTestId('divergence-next')); // 1→2
    fireEvent.click(screen.getByTestId('divergence-next')); // 2→3
    fireEvent.click(screen.getByTestId('divergence-next')); // 3→4
    // step 4 → submit button appears
    expect(screen.getByTestId('divergence-submit')).toBeTruthy();
  });

  it('picking the character-transform type + naming + Spawn submits a derive', async () => {
    deriveWorkMock.mockResolvedValue({ project_id: 'deriv', source_work_id: 'sw' });
    renderWizard();
    fireEvent.click(screen.getByTestId('divergence-next')); // →2
    fireEvent.click(screen.getByTestId('divergence-type-character_transform'));
    fireEvent.click(screen.getByTestId('divergence-next')); // →3
    fireEvent.click(screen.getByTestId('divergence-next')); // →4
    fireEvent.change(screen.getByTestId('divergence-name'), { target: { value: 'Genderbend AU' } });
    fireEvent.click(screen.getByTestId('divergence-submit'));
    // derive.mutate defers the mutationFn to a microtask — await the call.
    await waitFor(() =>
      expect(deriveWorkMock).toHaveBeenCalledWith('src-proj', expect.objectContaining({
        divergence: expect.objectContaining({ taxonomy: 'character_transform' }),
      }), 'tok'),
    );
  });
});
