// DOCK-9 migration — BatchTranslateDialog's hand-rolled `fixed inset-0` overlay was replaced
// with the shared FormDialog (see ResolveKindModal.test.tsx, the precedent for this migration).
// This test proves the FormDialog shell (Radix dialog role, Escape → onClose, footer submit
// button) still works; the EntityRow candidate rendering and useBatchTranslate hook logic are
// covered elsewhere (useBatchTranslate.test.tsx) and untouched by this migration.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { TranslationCandidateEntity } from '../../types';

const btMocks = vi.hoisted(() => ({
  submit: vi.fn(),
  selectLanguage: vi.fn(),
  setDraft: vi.fn(),
  state: {
    targetLanguage: 'en',
    candidates: [] as TranslationCandidateEntity[],
    total: 0,
    drafts: {} as Record<string, string>,
    loading: false,
    submitting: false,
    error: null as string | null,
    result: null as null | { translated: number; skipped_verified: number; skipped_empty: number; failed: unknown[] },
  },
}));

vi.mock('../../hooks/useBatchTranslate', () => ({
  useBatchTranslate: () => ({
    targetLanguage: btMocks.state.targetLanguage,
    selectLanguage: btMocks.selectLanguage,
    candidates: btMocks.state.candidates,
    total: btMocks.state.total,
    drafts: btMocks.state.drafts,
    setDraft: btMocks.setDraft,
    submit: btMocks.submit,
    loading: btMocks.state.loading,
    submitting: btMocks.state.submitting,
    error: btMocks.state.error,
    result: btMocks.state.result,
  }),
}));

import { BatchTranslateDialog } from '../BatchTranslateDialog';

const CANDIDATES: TranslationCandidateEntity[] = [
  {
    entity_id: 'e1',
    display_name: '焰魔',
    kind_code: 'character',
    status: 'active',
    attributes: [
      { attr_value_id: 'av-name', code: 'name', field_type: 'text', original_language: 'zh', original_value: '焰魔' },
    ],
  } as TranslationCandidateEntity,
];

function renderDialog(onClose = vi.fn()) {
  render(<BatchTranslateDialog bookId="book-1" onClose={onClose} />);
  return { onClose };
}

beforeEach(() => {
  btMocks.submit.mockReset().mockResolvedValue(undefined);
  btMocks.selectLanguage.mockReset();
  btMocks.setDraft.mockReset();
  btMocks.state = {
    targetLanguage: 'en',
    candidates: CANDIDATES,
    total: 1,
    drafts: {},
    loading: false,
    submitting: false,
    error: null,
    result: null,
  };
});

describe('BatchTranslateDialog (FormDialog adoption)', () => {
  it('renders as an accessible Radix dialog with the title and candidate rows', () => {
    renderDialog();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    // FormDialog's Gate-5-I2 fallback mirrors the title into an sr-only Description
    // when none is supplied, so the title text appears twice (visible Title + sr-only).
    expect(screen.getAllByText('batch_translate.title').length).toBeGreaterThan(0);
    // '焰魔' appears twice (candidate header + the attribute's original_value echo)
    expect(screen.getAllByText('焰魔').length).toBeGreaterThan(0);
  });

  it('Escape closes via onClose (no busy guard — preserves pre-migration behavior)', async () => {
    const { onClose } = renderDialog();
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('clicking "Apply translations" calls bt.submit()', () => {
    renderDialog();
    fireEvent.click(screen.getByText('batch_translate.apply'));
    expect(btMocks.submit).toHaveBeenCalled();
  });

  it('disables the submit button while submitting', () => {
    btMocks.state.submitting = true;
    renderDialog();
    expect(screen.getByText('batch_translate.apply').closest('button')).toBeDisabled();
  });

  it('disables the submit button when there are no candidates', () => {
    btMocks.state.candidates = [];
    renderDialog();
    expect(screen.getByText('batch_translate.apply').closest('button')).toBeDisabled();
  });

  it('shows the result summary in the footer once available', () => {
    btMocks.state.result = { translated: 2, skipped_verified: 1, skipped_empty: 0, failed: [] };
    renderDialog();
    expect(screen.getByText('batch_translate.result')).toBeInTheDocument();
  });
});
