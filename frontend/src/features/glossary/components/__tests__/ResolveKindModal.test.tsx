// 13_glossary_panels.md A4 — ResolveKindModal is the DOCK-9 adoption PRECEDENT: the first
// hand-rolled `fixed inset-0` migrated to the shared FormDialog. This test's main job is
// proving the migration didn't change dismissal semantics (Escape/backdrop via Radix) and, if
// anything, FIXED the original's inconsistency (Escape blocked mid-save, backdrop-click wasn't).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ResolveKindModal } from '../ResolveKindModal';
import type { EntityKind, UnknownEntity } from '../../types';

const KINDS: EntityKind[] = [
  { kind_id: 'k1', code: 'location', name: 'Location', icon: '📍' } as EntityKind,
];

const ENTITY: UnknownEntity = {
  entity_id: 'e1', name: '哪吒', source_kind_code: 'faction', status: 'draft', created_at: '2026-06-04T00:00:00Z',
} as UnknownEntity;

function renderModal(onResolve = vi.fn(), onClose = vi.fn()) {
  render(<ResolveKindModal entity={ENTITY} kinds={KINDS} sameCodeCount={1} onResolve={onResolve} onClose={onClose} />);
  return { onResolve, onClose };
}

beforeEach(() => vi.clearAllMocks());

describe('ResolveKindModal (FormDialog adoption)', () => {
  it('renders as an accessible Radix dialog with the entity name as the description', () => {
    renderModal();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('哪吒')).toBeInTheDocument();
  });

  it('Escape closes via onClose when idle', async () => {
    const { onClose } = renderModal();
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('Escape does NOT close mid-save (guard moved into onOpenChange, same intent as the original keydown guard)', async () => {
    let resolveApply!: () => void;
    const onResolve = vi.fn(() => new Promise<void>((res) => { resolveApply = res; }));
    const { onClose } = renderModal(onResolve);
    fireEvent.click(screen.getByTestId('resolve-apply'));
    await waitFor(() => expect(onResolve).toHaveBeenCalled());
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
    resolveApply();
  });

  it('the Cancel button still calls onClose directly (not routed through onOpenChange)', () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByText('unknown.cancel'));
    expect(onClose).toHaveBeenCalled();
  });
});
