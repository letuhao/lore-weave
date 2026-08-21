import { describe, it, expect, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { FormDialog } from '../FormDialog';

describe('FormDialog', () => {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    title: 'Create book',
  };

  it('renders title when open', () => {
    render(<FormDialog {...defaultProps}><div>form content</div></FormDialog>);
    // Use heading role to disambiguate from the sr-only description
    // fallback which mirrors the title text (Gate-5-I2).
    expect(screen.getByRole('heading', { name: 'Create book' })).toBeInTheDocument();
  });

  it('always renders an accessible Description (Gate-5-I2)', () => {
    // Without a `description` prop the dialog must still emit a
    // Radix Dialog.Description so screen readers and Radix's own
    // aria-describedby check are satisfied. The fallback content
    // mirrors the title, but is sr-only so it doesn't change the
    // visual layout.
    render(
      <FormDialog {...defaultProps}><div>content</div></FormDialog>,
    );
    const dialog = screen.getByRole('dialog');
    const describedById = dialog.getAttribute('aria-describedby');
    expect(describedById).toBeTruthy();
    const desc = document.getElementById(describedById!);
    expect(desc).not.toBeNull();
    expect(desc).toHaveClass('sr-only');
    expect(desc?.textContent).toBe('Create book');
  });

  it('renders children', () => {
    render(<FormDialog {...defaultProps}><input placeholder="Book title" /></FormDialog>);
    expect(screen.getByPlaceholderText('Book title')).toBeInTheDocument();
  });

  it('renders description when provided', () => {
    render(
      <FormDialog {...defaultProps} description="Fill in the details">
        <div>content</div>
      </FormDialog>,
    );
    expect(screen.getByText('Fill in the details')).toBeInTheDocument();
  });

  it('renders footer when provided', () => {
    render(
      <FormDialog {...defaultProps} footer={<button>Save</button>}>
        <div>content</div>
      </FormDialog>,
    );
    expect(screen.getByText('Save')).toBeInTheDocument();
  });

  it('does not render when closed', () => {
    render(
      <FormDialog {...defaultProps} open={false}>
        <div>content</div>
      </FormDialog>,
    );
    expect(screen.queryByText('Create book')).not.toBeInTheDocument();
  });

  it('has a close button with aria-label', () => {
    render(<FormDialog {...defaultProps}><div>content</div></FormDialog>);
    expect(screen.getByLabelText('Close')).toBeInTheDocument();
  });

  // ── C0 (BL-4/KN-3): scroll + pinned footer ──
  // The dialog caps its height and scrolls the BODY only; the footer is pinned
  // and a SIBLING of the scroll region (adversary: must not be nested inside it,
  // else the action scrolls away or overlaps content on tall forms).
  // A form may hold partially completed work, so a stray click on the backdrop must
  // not discard it. Asserted through Radix's real dismissal path — a pointerdown
  // OUTSIDE the content, which is what `onInteractOutside` intercepts. (An earlier
  // version of this test looked up `[data-radix-dialog-overlay]`, an attribute Radix
  // does not emit: the query returned null and the test failed before it could
  // exercise anything.)
  it('does not close when the backdrop is clicked', async () => {
    const onOpenChange = vi.fn();
    render(
      <FormDialog {...defaultProps} onOpenChange={onOpenChange}>
        <div>content</div>
      </FormDialog>,
    );
    // Two details decide whether this test can fail at all, and both were got wrong
    // before: Radix's DismissableLayer registers its outside-pointer listener inside a
    // `setTimeout`, so a synchronous fire lands before the listener exists; and the
    // dismissal needs the full press+release, not `pointerDown` alone. Miss either and
    // the assertion below is green even with `onInteractOutside` deleted.
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)); });
    fireEvent.pointerDown(document.body);
    fireEvent.click(document.body);

    expect(onOpenChange).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  // The other half of the same decision: suppressing outside-dismissal must not
  // strip the deliberate ways out, or the dialog becomes a trap.
  it('still closes on Escape', () => {
    const onOpenChange = vi.fn();
    render(
      <FormDialog {...defaultProps} onOpenChange={onOpenChange}>
        <div>content</div>
      </FormDialog>,
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('caps height and makes the body scrollable (C0)', () => {
    render(
      <FormDialog {...defaultProps}>
        <div data-testid="body">tall content</div>
      </FormDialog>,
    );
    expect(screen.getByRole('dialog').className).toContain('max-h-[85vh]');
    const scrollRegion = screen.getByTestId('body').parentElement!;
    expect(scrollRegion.className).toContain('overflow-y-auto');
    expect(scrollRegion.className).toContain('flex-1');
  });

  it('pins the footer as a sibling of the scroll body (C0)', () => {
    render(
      <FormDialog {...defaultProps} footer={<button data-testid="submit">Save</button>}>
        <div data-testid="body">content</div>
      </FormDialog>,
    );
    const scrollRegion = screen.getByTestId('body').parentElement!;
    const footerWrap = screen.getByTestId('submit').parentElement!;
    expect(footerWrap.className).toContain('flex-shrink-0');
    expect(scrollRegion.contains(footerWrap)).toBe(false);
    expect(scrollRegion.parentElement).toBe(footerWrap.parentElement);
  });

  // dockable-gui.md DOCK-9 — adopting this shared dialog (instead of a hand-rolled
  // `fixed inset-0`) must not force every caller into the original max-w-lg width.
  it('defaults to max-w-lg (same rendered width as every pre-existing call site)', () => {
    render(<FormDialog {...defaultProps}><div>content</div></FormDialog>);
    expect(screen.getByRole('dialog').className).toContain('max-w-lg');
  });

  it('honors a wider size for multi-column/wizard content', () => {
    render(
      <FormDialog {...defaultProps} size="3xl"><div>content</div></FormDialog>,
    );
    const dialogClass = screen.getByRole('dialog').className;
    expect(dialogClass).toContain('max-w-3xl');
    expect(dialogClass).not.toContain('max-w-lg');
  });
});
