import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
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
});
