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
    expect(screen.getByText('Create book')).toBeInTheDocument();
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
