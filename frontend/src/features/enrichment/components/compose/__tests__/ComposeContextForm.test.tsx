import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { ComposeContextForm } from '../ComposeContextForm';

describe('ComposeContextForm', () => {
  it('reports text + license changes to the parent', () => {
    const onText = vi.fn();
    const onLicense = vi.fn();
    render(
      <ComposeContextForm
        contextText="東海仙山。"
        onContextTextChange={onText}
        license="public_domain"
        onLicenseChange={onLicense}
      />,
    );
    fireEvent.change(screen.getByTestId('compose-context-text'), { target: { value: '新內容' } });
    expect(onText).toHaveBeenCalledWith('新內容');
    fireEvent.change(screen.getByTestId('compose-context-license'), { target: { value: 'owned' } });
    expect(onLicense).toHaveBeenCalledWith('owned');
  });

  it('shows the copyrighted warning only when copyrighted is selected', () => {
    const { rerender } = render(
      <ComposeContextForm contextText="" onContextTextChange={vi.fn()} license="public_domain" onLicenseChange={vi.fn()} />,
    );
    expect(screen.queryByTestId('compose-context-copyright-warning')).toBeNull();
    rerender(
      <ComposeContextForm contextText="" onContextTextChange={vi.fn()} license="copyrighted" onLicenseChange={vi.fn()} />,
    );
    expect(screen.getByTestId('compose-context-copyright-warning')).toBeInTheDocument();
  });

  it('offers all four license options', () => {
    render(
      <ComposeContextForm contextText="" onContextTextChange={vi.fn()} license="public_domain" onLicenseChange={vi.fn()} />,
    );
    const opts = within(screen.getByTestId('compose-context-license')).getAllByRole('option').map((o) => o.getAttribute('value'));
    expect(opts).toEqual(['public_domain', 'licensed', 'owned', 'copyrighted']);
  });
});
