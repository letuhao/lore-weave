import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LanguageDisplay } from '../LanguageDisplay';

describe('LanguageDisplay', () => {
  it('renders inline variant by default', () => {
    render(<LanguageDisplay code="ja" />);
    expect(screen.getByText(/日本語/)).toBeInTheDocument();
    expect(screen.getByText('(ja)')).toBeInTheDocument();
  });

  it('renders stacked variant', () => {
    render(<LanguageDisplay code="vi" variant="stacked" />);
    expect(screen.getByText('Tiếng Việt')).toBeInTheDocument();
    expect(screen.getByText('(vi)')).toBeInTheDocument();
  });

  it('falls back to code for unknown language', () => {
    const { container } = render(<LanguageDisplay code="xx" />);
    // "xx" appears as both the name and the code suffix "(xx)"
    expect(container.textContent).toContain('xx');
    expect(container.textContent).toContain('(xx)');
  });

  it('applies additional className', () => {
    const { container } = render(<LanguageDisplay code="en" className="my-class" />);
    expect(container.firstChild).toHaveClass('my-class');
  });
});
