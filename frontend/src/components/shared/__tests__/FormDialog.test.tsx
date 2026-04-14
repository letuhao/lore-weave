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
});
