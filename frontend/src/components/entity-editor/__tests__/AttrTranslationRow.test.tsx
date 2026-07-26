import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { Translation } from '@/features/glossary/types';

// S6 — per-language alias editor. The `aliases` attribute (field_type `tags`) edits its
// per-language SET as chips, persisted as a JSON ARRAY STRING — the exact format the BE
// glossary_propose_aliases writer and composePerLanguageAliases reader expect.

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMocks }));

const apiMocks = vi.hoisted(() => ({
  createTranslation: vi.fn(),
  patchTranslation: vi.fn(),
  deleteTranslation: vi.fn(),
}));
vi.mock('@/features/glossary/api', () => ({ glossaryApi: apiMocks }));

import { AttrTranslationRow } from '../AttrTranslationRow';

function tr(value: string): Translation {
  return {
    translation_id: 't1', attr_value_id: 'av1', language_code: 'en',
    value, confidence: 'draft', translator: 'assistant', updated_at: '2026-06-21T00:00:00Z',
  };
}

const baseProps = {
  bookId: 'b1', entityId: 'e1', attrValueId: 'av1', language: 'en',
  onChanged: vi.fn(),
};

describe('AttrTranslationRow — per-language alias tags (S6)', () => {
  beforeEach(() => {
    toastMocks.success.mockReset();
    toastMocks.error.mockReset();
    apiMocks.createTranslation.mockReset();
    apiMocks.patchTranslation.mockReset();
    apiMocks.deleteTranslation.mockReset();
  });

  it('renders the existing alias SET as chips from a JSON array value', () => {
    render(
      <AttrTranslationRow
        {...baseProps}
        attrCode="aliases"
        translation={tr('["Flame Demon","Yan Mo"]')}
        onChanged={vi.fn()}
      />,
    );
    expect(screen.getByText('Flame Demon')).toBeInTheDocument();
    expect(screen.getByText('Yan Mo')).toBeInTheDocument();
    // The chip editor is shown, NOT the raw textarea.
    expect(screen.queryByPlaceholderText('translation_row.placeholder')).not.toBeInTheDocument();
  });

  it('dedupes a value that arrived with duplicate aliases (no React key collision)', () => {
    render(
      <AttrTranslationRow {...baseProps} attrCode="aliases" translation={tr('["A","A","B"]')} onChanged={vi.fn()} />,
    );
    expect(screen.getAllByText('A')).toHaveLength(1);
    expect(screen.getByText('B')).toBeInTheDocument();
  });

  it('keeps the plain textarea for a NON-aliases tags attribute (members/tropes stay CSV)', () => {
    // Scope guard: only `aliases` is JSON. A `members` tags attr must NOT become a chip
    // editor, or its translation would store JSON while its source stays CSV.
    render(
      <AttrTranslationRow {...baseProps} attrCode="members" translation={tr('Alice, Bob')} onChanged={vi.fn()} />,
    );
    expect(screen.getByPlaceholderText('translation_row.placeholder')).toHaveValue('Alice, Bob');
    expect(screen.queryByPlaceholderText('translation_row.tags_add')).not.toBeInTheDocument();
  });

  it('creates a translation whose value is a JSON array string when a tag is added + saved', async () => {
    apiMocks.createTranslation.mockResolvedValue(tr('["Ghost"]'));
    const onChanged = vi.fn();
    render(
      <AttrTranslationRow {...baseProps} attrCode="aliases" translation={undefined} onChanged={onChanged} />,
    );
    const add = screen.getByPlaceholderText('translation_row.tags_add');
    fireEvent.change(add, { target: { value: 'Ghost' } });
    fireEvent.keyDown(add, { key: 'Enter' });
    expect(screen.getByText('Ghost')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'translation_row.save' }));
    await waitFor(() => expect(apiMocks.createTranslation).toHaveBeenCalledTimes(1));
    expect(apiMocks.createTranslation).toHaveBeenCalledWith(
      'b1', 'e1', 'av1',
      { language_code: 'en', value: '["Ghost"]', confidence: 'draft' },
      'tok',
    );
    expect(onChanged).toHaveBeenCalled();
  });

  it('patches with the updated JSON array when a chip is removed + saved', async () => {
    apiMocks.patchTranslation.mockResolvedValue(tr('["Yan Mo"]'));
    render(
      <AttrTranslationRow
        {...baseProps}
        attrCode="aliases"
        translation={tr('["Flame Demon","Yan Mo"]')}
        onChanged={vi.fn()}
      />,
    );
    // Remove the "Flame Demon" chip — its delete button is the sibling X inside the chip.
    const chip = screen.getByText('Flame Demon').closest('span')!;
    fireEvent.click(chip.querySelector('button')!);
    expect(screen.queryByText('Flame Demon')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'translation_row.save' }));
    await waitFor(() => expect(apiMocks.patchTranslation).toHaveBeenCalledTimes(1));
    expect(apiMocks.patchTranslation).toHaveBeenCalledWith(
      'b1', 'e1', 'av1', 't1', { value: '["Yan Mo"]' }, 'tok',
    );
  });

  it('falls back to the raw textarea for a non-array (legacy) value — no silent drop', () => {
    render(
      <AttrTranslationRow
        {...baseProps}
        attrCode="aliases"
        translation={tr('legacy plain string')}
        onChanged={vi.fn()}
      />,
    );
    const textarea = screen.getByPlaceholderText('translation_row.placeholder');
    expect(textarea).toHaveValue('legacy plain string');
    expect(screen.queryByPlaceholderText('translation_row.tags_add')).not.toBeInTheDocument();
  });

  it('uses the plain textarea for non-tags attributes', () => {
    render(
      <AttrTranslationRow {...baseProps} attrCode="description" translation={tr('Hello')} onChanged={vi.fn()} />,
    );
    expect(screen.getByPlaceholderText('translation_row.placeholder')).toHaveValue('Hello');
    expect(screen.queryByPlaceholderText('translation_row.tags_add')).not.toBeInTheDocument();
  });
});
