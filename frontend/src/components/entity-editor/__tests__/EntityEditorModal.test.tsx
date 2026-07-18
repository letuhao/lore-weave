import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { GlossaryEntity } from '@/features/glossary/types';

// EntityEditorModal DOCK-9 adoption (13_glossary_panels.md A1) — swapped the hand-rolled
// `fixed inset-0` backdrop+panel pair for raw @radix-ui/react-dialog primitives, and moved
// its load/save state into the shared `useGlossaryEntity` hook. The regression risk this
// test exists to catch: Radix's built-in Escape/outside-click dismissal must still call
// `onClose` now that the manual keydown listener is gone.

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const apiMocks = vi.hoisted(() => ({
  getEntity: vi.fn(),
  patchAttributeValue: vi.fn(),
  patchEntity: vi.fn(),
}));
vi.mock('@/features/glossary/api', () => ({ glossaryApi: apiMocks }));
// S-06 — the modal now mounts AddAttributeValueSection, which reads the book ontology via
// react-query. Stub it (empty ⇒ the add-section renders nothing) so these tests need no QueryClient.
vi.mock('@/features/glossary/hooks/useBookOntology', () => ({
  useBookOntology: () => ({ ontology: { genres: [], kinds: [], attributes: [] }, isLoading: false }),
}));

import { toast } from 'sonner';
import { EntityEditorModal } from '../EntityEditorModal';

const BOOK = 'book-1';
const ENTITY_ID = 'entity-1';

function entity(): GlossaryEntity {
  return {
    entity_id: ENTITY_ID,
    book_id: BOOK,
    kind_id: 'kind-1',
    kind: { kind_id: 'kind-1', code: 'character', name: 'Character', icon: '🧑', color: '#fff' },
    display_name: 'Jiang Ziya',
    display_name_translation: null,
    status: 'draft',
    tags: [],
    chapter_link_count: 0,
    translation_count: 0,
    evidence_count: 0,
    created_at: '2026-07-04T00:00:00Z',
    updated_at: '2026-07-04T00:00:00Z',
    chapter_links: [],
    attribute_values: [
      {
        attr_value_id: 'av-1',
        entity_id: ENTITY_ID,
        attr_def_id: 'def-1',
        attribute_def: {
          attr_def_id: 'def-1', code: 'title', name: 'Title', field_type: 'text',
          is_required: false, is_system: false, is_active: true, sort_order: 0, genre_tags: [],
        },
        original_language: 'en',
        original_value: 'Immortal',
        translations: [],
        evidences: [],
      },
    ],
  };
}

function baseProps() {
  return {
    bookId: BOOK,
    entityId: ENTITY_ID,
    onClose: vi.fn(),
    onSaved: vi.fn(),
    onDelete: vi.fn(),
  };
}

beforeEach(() => {
  Object.values(apiMocks).forEach((m) => m.mockReset());
  vi.mocked(toast.success).mockReset();
  vi.mocked(toast.error).mockReset();
  apiMocks.getEntity.mockResolvedValue(entity());
  apiMocks.patchAttributeValue.mockResolvedValue({});
});

describe('EntityEditorModal (Radix Dialog adoption)', () => {
  it('renders the entity title and its attribute once loaded', async () => {
    render(<EntityEditorModal {...baseProps()} />);
    const titles = await screen.findAllByText('Jiang Ziya');
    expect(titles.length).toBeGreaterThan(0);
    expect(screen.getByDisplayValue('Immortal')).toBeInTheDocument();
  });

  it('Escape closes the dialog via onClose (Radix default — no manual keydown listener anymore)', async () => {
    const props = baseProps();
    render(<EntityEditorModal {...props} />);
    await screen.findAllByText('Jiang Ziya');
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(props.onClose).toHaveBeenCalled());
  });

  it('editing an attribute then saving persists via patchAttributeValue and notifies onSaved', async () => {
    const props = baseProps();
    render(<EntityEditorModal {...props} />);
    const input = await screen.findByDisplayValue('Immortal');
    fireEvent.change(input, { target: { value: 'Deity' } });

    const saveButtons = screen.getAllByText('modal.save');
    fireEvent.click(saveButtons[0]);

    await waitFor(() => expect(apiMocks.patchAttributeValue).toHaveBeenCalledWith(
      BOOK, ENTITY_ID, 'av-1', { original_value: 'Deity' }, 'tok',
    ));
    await waitFor(() => expect(props.onSaved).toHaveBeenCalled());
    expect(toast.success).toHaveBeenCalledWith('modal.toast.saved');
  });

  it('a save failure toasts an error and keeps the dialog open (no onClose call)', async () => {
    const props = baseProps();
    apiMocks.patchAttributeValue.mockRejectedValue(new Error('conflict'));
    render(<EntityEditorModal {...props} />);
    const input = await screen.findByDisplayValue('Immortal');
    fireEvent.change(input, { target: { value: 'Deity' } });
    fireEvent.click(screen.getAllByText('modal.save')[0]);

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('conflict'));
    expect(props.onClose).not.toHaveBeenCalled();
  });

  it('switching to the status select persists the new status', async () => {
    const props = baseProps();
    apiMocks.patchEntity.mockResolvedValue(entity());
    render(<EntityEditorModal {...props} />);
    await screen.findAllByText('Jiang Ziya');
    const statusSelect = screen.getByDisplayValue('modal.status.draft');
    fireEvent.change(statusSelect, { target: { value: 'active' } });
    await waitFor(() => expect(apiMocks.patchEntity).toHaveBeenCalledWith(BOOK, ENTITY_ID, { status: 'active' }, 'tok'));
    await waitFor(() => expect(props.onSaved).toHaveBeenCalled());
  });

  it('blurring the scope_label field with a new value persists it', async () => {
    const props = baseProps();
    apiMocks.patchEntity.mockResolvedValue(entity());
    render(<EntityEditorModal {...props} />);
    await screen.findAllByText('Jiang Ziya');
    const scopeInput = screen.getByLabelText('modal.scope_label.aria');
    fireEvent.change(scopeInput, { target: { value: 'World A' } });
    fireEvent.blur(scopeInput);
    await waitFor(() => expect(apiMocks.patchEntity).toHaveBeenCalledWith(BOOK, ENTITY_ID, { scope_label: 'World A' }, 'tok'));
    await waitFor(() => expect(props.onSaved).toHaveBeenCalled());
  });

  it('blurring the scope_label field with an UNCHANGED value does not call the API', async () => {
    const props = baseProps();
    render(<EntityEditorModal {...props} />);
    await screen.findAllByText('Jiang Ziya');
    const scopeInput = screen.getByLabelText('modal.scope_label.aria');
    fireEvent.blur(scopeInput);
    await waitFor(() => expect(screen.getByDisplayValue('Immortal')).toBeInTheDocument());
    expect(apiMocks.patchEntity).not.toHaveBeenCalled();
  });

  it('a colliding scope_label toasts the backend error without closing the dialog', async () => {
    const props = baseProps();
    apiMocks.patchEntity.mockRejectedValue(new Error('an entity with this name, kind, and scope already exists in this book'));
    render(<EntityEditorModal {...props} />);
    await screen.findAllByText('Jiang Ziya');
    const scopeInput = screen.getByLabelText('modal.scope_label.aria');
    fireEvent.change(scopeInput, { target: { value: 'World B' } });
    fireEvent.blur(scopeInput);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('an entity with this name, kind, and scope already exists in this book'));
    expect(props.onClose).not.toHaveBeenCalled();
  });

  // /review-impl MED fix (2026-07-09): the field is now controlled and must revert
  // to the entity's TRUE (unchanged) scope_label after a rejected edit — previously
  // (uncontrolled, defaultValue) it kept showing the failed value as if it stuck.
  it('reverts the displayed scope_label to the real value after a rejected edit', async () => {
    const props = baseProps();
    apiMocks.patchEntity.mockRejectedValue(new Error('an entity with this name, kind, and scope already exists in this book'));
    render(<EntityEditorModal {...props} />);
    await screen.findAllByText('Jiang Ziya');
    const scopeInput = screen.getByLabelText('modal.scope_label.aria') as HTMLInputElement;
    expect(scopeInput.value).toBe('');
    fireEvent.change(scopeInput, { target: { value: 'World B' } });
    fireEvent.blur(scopeInput);
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    await waitFor(() => expect(scopeInput.value).toBe(''));
  });
});
