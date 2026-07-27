// The author's marking flow (atom-edit Phase D, D3d).
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const create = vi.fn();
vi.mock('../../errorBlocks', async () => {
  const actual = await vi.importActual<typeof import('../../errorBlocks')>('../../errorBlocks');
  return { ...actual, errorBlocksApi: { create: (...a: unknown[]) => create(...a) } };
});

const toastError = vi.fn();
const toastSuccess = vi.fn();
vi.mock('sonner', () => ({ toast: { error: (m: string) => toastError(m), success: (m: string) => toastSuccess(m) } }));

// Local i18n mock: `t(key, {defaultValue})` must return the defaultValue, so a dropped option
// object shows up as a missing string rather than silently rendering the raw key.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? _k,
  }),
}));

import { MarkErrorBlockAction } from '../MarkErrorBlockAction';

/** A fake editor whose selection covers "The hall went quiet." in block 1. */
function fakeEditor(sel = { from: 27, to: 47 }) {
  const texts = ['Elara opened the ledger.', 'The hall went quiet.'];
  const starts = [1, 27];
  return {
    getJSON: () => ({
      type: 'doc',
      content: texts.map((text) => ({ type: 'paragraph', content: [{ type: 'text', text }] })),
    }),
    state: {
      selection: sel,
      doc: {
        resolve: (p: number) => {
          const idx = p >= starts[1] ? 1 : 0;
          return { depth: 1, index: () => idx, start: () => starts[idx] };
        },
        textBetween: (a: number, b: number) => texts[1].slice(a - starts[1], a - starts[1] + (b - a)),
      },
    },
  } as never;
}

const props = { projectId: 'p1', chapterId: 'ch1', token: 'tok' };

beforeEach(() => {
  create.mockReset();
  toastError.mockReset();
  toastSuccess.mockReset();
});

describe('MarkErrorBlockAction', () => {
  it('renders nothing without a chapter — no dead affordance', () => {
    const { container } = render(
      <MarkErrorBlockAction editor={fakeEditor()} {...props} chapterId={null} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('opens the note form from the toolbar button', () => {
    render(<MarkErrorBlockAction editor={fakeEditor()} {...props} />);
    fireEvent.click(screen.getByTestId('selection-mark-error'));
    expect(screen.getByTestId('mark-error-form')).toBeInTheDocument();
  });

  it('sends the span, the note and the kind — the whole anchor triple', async () => {
    create.mockResolvedValue({ id: 'b1' });
    render(<MarkErrorBlockAction editor={fakeEditor()} {...props} />);
    fireEvent.click(screen.getByTestId('selection-mark-error'));
    fireEvent.change(screen.getByTestId('mark-error-note'), {
      target: { value: 'she died in ch3' },
    });
    fireEvent.change(screen.getByTestId('mark-error-kind'), { target: { value: 'continuity' } });
    fireEvent.click(screen.getByTestId('mark-error-save'));

    await waitFor(() => expect(create).toHaveBeenCalled());
    const [projectId, chapterId, body] = create.mock.calls[0];
    expect(projectId).toBe('p1');
    expect(chapterId).toBe('ch1');
    expect(body.quote).toBe('The hall went quiet.');
    expect(body.note).toBe('she died in ch3');
    expect(body.kind).toBe('continuity');
    // The offsets must address the SECOND block in the flattened text, not the first.
    expect(body.start_offset).toBe('Elara opened the ledger.\n\n'.length);
    expect(body.source_fingerprint).toBeTruthy();
  });

  it('refuses an empty note — a mark with no note is just a highlight', async () => {
    render(<MarkErrorBlockAction editor={fakeEditor()} {...props} />);
    fireEvent.click(screen.getByTestId('selection-mark-error'));
    fireEvent.click(screen.getByTestId('mark-error-save'));
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(create).not.toHaveBeenCalled();
  });

  it('refuses an empty selection rather than creating an unanchorable mark', async () => {
    render(<MarkErrorBlockAction editor={fakeEditor({ from: 27, to: 27 })} {...props} />);
    fireEvent.click(screen.getByTestId('selection-mark-error'));
    fireEvent.change(screen.getByTestId('mark-error-note'), { target: { value: 'wrong' } });
    fireEvent.click(screen.getByTestId('mark-error-save'));
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(create).not.toHaveBeenCalled();
  });

  it('reads the selection at SUBMIT time, not when the form opened', async () => {
    // The author can adjust the selection while typing the note. Marking the span captured at
    // open would record a complaint about prose they are no longer pointing at.
    create.mockResolvedValue({ id: 'b1' });
    const editor = fakeEditor();
    const { rerender } = render(<MarkErrorBlockAction editor={editor} {...props} />);
    fireEvent.click(screen.getByTestId('selection-mark-error'));
    fireEvent.change(screen.getByTestId('mark-error-note'), { target: { value: 'too flat' } });

    const moved = fakeEditor({ from: 27, to: 35 });   // now only "The hall"
    rerender(<MarkErrorBlockAction editor={moved} {...props} />);
    fireEvent.click(screen.getByTestId('mark-error-save'));

    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0][2].quote).toBe('The hall');
  });

  it('says a duplicate is a duplicate, not a generic failure', async () => {
    create.mockRejectedValue(new Error('409 duplicate'));
    render(<MarkErrorBlockAction editor={fakeEditor()} {...props} />);
    fireEvent.click(screen.getByTestId('selection-mark-error'));
    fireEvent.change(screen.getByTestId('mark-error-note'), { target: { value: 'x' } });
    fireEvent.click(screen.getByTestId('mark-error-save'));
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(toastError.mock.calls[0][0]).toMatch(/already marked/i);
  });
});
