// DF6 — "What I know" + Recall: remembered entities render, the search box drives recall, empty +
// private states are honest. DF7 / D17 — a person carries a Forget action gated by a worded confirm.
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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

  // DF7 / D17 — Forget is a two-step, worded confirm (irreversible); it calls onForget with the NAME.
  it('forgets a person only after a worded confirm, calling onForget with the name', async () => {
    const onForget = vi.fn().mockResolvedValue({ forgotten: true });
    renderOpen({ entities: [ent('e1', 'Minh', 'colleague')], onForget });

    // Step 1: no confirm shown until Forget is pressed; the destructive call has NOT fired.
    expect(screen.queryByTestId('memory-forget-confirm-e1')).toBeNull();
    fireEvent.click(screen.getByTestId('memory-forget-e1'));
    expect(screen.getByTestId('memory-forget-confirm-e1')).toBeTruthy();
    expect(onForget).not.toHaveBeenCalled();

    // Step 2: confirming fires onForget with the display name.
    fireEvent.click(screen.getByTestId('memory-forget-do-e1'));
    expect(onForget).toHaveBeenCalledWith('Minh');
    await waitFor(() => expect(screen.queryByTestId('memory-forget-confirm-e1')).toBeNull());
  });

  it('Keep cancels the confirm without forgetting', () => {
    const onForget = vi.fn();
    renderOpen({ entities: [ent('e1', 'Minh', 'colleague')], onForget });
    fireEvent.click(screen.getByTestId('memory-forget-e1'));
    fireEvent.click(screen.getByTestId('memory-forget-keep-e1'));
    expect(screen.queryByTestId('memory-forget-confirm-e1')).toBeNull();
    expect(onForget).not.toHaveBeenCalled();
  });

  it('offers Forget only for people, not projects', () => {
    renderOpen({ entities: [ent('e2', 'Q3 Billing', 'project')], onForget: vi.fn() });
    expect(screen.queryByTestId('memory-forget-e2')).toBeNull(); // a project has no "forget a person"
  });

  it('offers no Forget action when no onForget handler is wired', () => {
    renderOpen({ entities: [ent('e1', 'Minh', 'colleague')] });
    expect(screen.queryByTestId('memory-forget-e1')).toBeNull();
  });
});
