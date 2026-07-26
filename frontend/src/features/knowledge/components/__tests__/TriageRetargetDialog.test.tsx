import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// S-05b (F1) — the entity picker that replaces the re_target UUID prompt.
vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }),
}));

const useEntitiesMock = vi.fn();
vi.mock('../../hooks/useEntities', () => ({
  useEntities: (...a: unknown[]) => useEntitiesMock(...a),
}));

// no real debounce delay in the test
vi.mock('../../hooks/useDebouncedValue', () => ({
  useDebouncedValue: (v: string) => v,
}));

import { TriageRetargetDialog } from '../TriageRetargetDialog';

describe('TriageRetargetDialog', () => {
  beforeEach(() => {
    useEntitiesMock.mockReset();
    useEntitiesMock.mockReturnValue({
      entities: [
        { id: 'ent-a', name: 'Aria', kind: 'character' },
        { id: 'ent-b', name: 'Borin', kind: 'character' },
      ],
    });
  });

  it('searches, lets me pick an entity by NAME, and returns its id (never a UUID prompt)', async () => {
    const onPick = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <TriageRetargetDialog open projectId="p-1" onPick={onPick} onOpenChange={onOpenChange} />,
    );
    // typing >=2 chars reveals the candidate list
    fireEvent.change(screen.getByTestId('triage-retarget-search'), {
      target: { value: 'ar' },
    });
    await waitFor(() => screen.getByTestId('triage-retarget-option-ent-a'));
    // confirm is disabled until a pick
    expect((screen.getByTestId('triage-retarget-confirm') as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByTestId('triage-retarget-option-ent-a'));
    fireEvent.click(screen.getByTestId('triage-retarget-confirm'));
    expect(onPick).toHaveBeenCalledWith('ent-a');
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('confirm does nothing with no selection (no silent no-op)', () => {
    const onPick = vi.fn();
    render(
      <TriageRetargetDialog open projectId="p-1" onPick={onPick} onOpenChange={vi.fn()} />,
    );
    // confirm is disabled with nothing picked
    expect((screen.getByTestId('triage-retarget-confirm') as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByTestId('triage-retarget-confirm'));
    expect(onPick).not.toHaveBeenCalled();
  });
});
