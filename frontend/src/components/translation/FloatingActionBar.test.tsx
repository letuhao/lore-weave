import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { FloatingActionBar } from './FloatingActionBar';

describe('FloatingActionBar', () => {
  beforeEach(() => { cleanup(); });

  // ── Visibility ────────────────────────────────────────────────────────────

  it('renders nothing when selectedCount is 0', () => {
    const { container } = render(
      <FloatingActionBar selectedCount={0} onTranslate={vi.fn()} onClear={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders bar when selectedCount is 1', () => {
    render(<FloatingActionBar selectedCount={1} onTranslate={vi.fn()} onClear={vi.fn()} />);
    expect(screen.getByText('1 chapter selected')).toBeInTheDocument();
  });

  it('renders bar when selectedCount is greater than 1', () => {
    render(<FloatingActionBar selectedCount={5} onTranslate={vi.fn()} onClear={vi.fn()} />);
    expect(screen.getByText('5 chapters selected')).toBeInTheDocument();
  });

  // ── Singular / plural ─────────────────────────────────────────────────────

  it('uses singular "chapter" when count is 1', () => {
    render(<FloatingActionBar selectedCount={1} onTranslate={vi.fn()} onClear={vi.fn()} />);
    expect(screen.getByText('1 chapter selected')).toBeInTheDocument();
  });

  it('uses plural "chapters" when count is 3', () => {
    render(<FloatingActionBar selectedCount={3} onTranslate={vi.fn()} onClear={vi.fn()} />);
    expect(screen.getByText('3 chapters selected')).toBeInTheDocument();
  });

  // ── Buttons ───────────────────────────────────────────────────────────────

  it('renders Translate and Clear buttons', () => {
    render(<FloatingActionBar selectedCount={2} onTranslate={vi.fn()} onClear={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Translate' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Clear' })).toBeInTheDocument();
  });

  it('calls onTranslate when Translate button is clicked', () => {
    const onTranslate = vi.fn();
    render(<FloatingActionBar selectedCount={2} onTranslate={onTranslate} onClear={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Translate' }));
    expect(onTranslate).toHaveBeenCalledOnce();
  });

  it('calls onClear when Clear button is clicked', () => {
    const onClear = vi.fn();
    render(<FloatingActionBar selectedCount={2} onTranslate={vi.fn()} onClear={onClear} />);
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    expect(onClear).toHaveBeenCalledOnce();
  });

  it('onTranslate is not called by clicking Clear', () => {
    const onTranslate = vi.fn();
    render(<FloatingActionBar selectedCount={2} onTranslate={onTranslate} onClear={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    expect(onTranslate).not.toHaveBeenCalled();
  });
});
