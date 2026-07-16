// DF6 — "What I know" + Recall: remembered entities render, the search box drives recall, empty +
// private states are honest.
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi } from 'vitest';

import { MobileMemorySheet } from '../MobileMemorySheet';
import type { GlossaryEntitySummary } from '@/features/glossary/types';

const ent = (id: string, name: string, code: string): GlossaryEntitySummary =>
  ({ entity_id: id, display_name: name, short_description: 'note', kind: { code, name: code } } as unknown as GlossaryEntitySummary);

function renderOpen(props: Partial<Parameters<typeof MobileMemorySheet>[0]> = {}) {
  const base = { entities: [], loading: false, error: null, search: '', onSearch: vi.fn() };
  return render(
    <MemoryRouter initialEntries={['/assistant?sheet=memory']}>
      <MobileMemorySheet {...base} {...props} />
    </MemoryRouter>,
  );
}

describe('MobileMemorySheet (DF6)', () => {
  it('renders remembered entities with a private label', () => {
    renderOpen({ entities: [ent('e1', 'Minh', 'colleague'), ent('e2', 'Q3 Billing', 'project')] });
    expect(screen.getByTestId('memory-list').querySelectorAll('li').length).toBe(2);
    expect(screen.getByText('Minh')).toBeTruthy();
    expect(screen.getByText(/Private/)).toBeTruthy(); // never-shared framing
  });

  it('the search box drives recall (onSearch)', () => {
    const onSearch = vi.fn();
    renderOpen({ onSearch });
    fireEvent.change(screen.getByTestId('memory-search'), { target: { value: 'launch' } });
    expect(onSearch).toHaveBeenCalledWith('launch');
  });

  it('shows an honest empty state (and a search-specific one)', () => {
    renderOpen({ entities: [] });
    expect(screen.getByText(/Nothing kept yet/)).toBeTruthy();
    renderOpen({ entities: [], search: 'zzz' });
    expect(screen.getByText(/Nothing remembered matches/)).toBeTruthy();
  });
});
