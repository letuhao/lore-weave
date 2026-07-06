import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// Stub the heavy ModelPicker (fetches models) — clicking it selects a model.
vi.mock('@/components/model-picker', () => ({
  ModelPicker: ({ onChange }: { onChange: (id: string) => void }) => (
    <button type="button" data-testid="pick-model" onClick={() => onChange('m1')}>pick</button>
  ),
}));

const proposeMock = vi.fn();
vi.mock('../../../hooks/useGraphSchema', () => ({
  useSchemaPropose: () => ({ propose: proposeMock, isProposing: false }),
}));

import { GenerateSchemaDialog } from '../GenerateSchemaDialog';

beforeEach(() => proposeMock.mockReset());

describe('GenerateSchemaDialog (M3b — propose→confirm)', () => {
  // 14_kg_panels.md K8 (DOCK-9) — this dialog is mounted only while `showGenerate`
  // is true (SchemaWorkbench), so it's always `open`; unlike VersionsPanel's
  // closed-by-default dialogs, asserting "no fixed inset-0 in the rendered HTML"
  // doesn't apply here (Radix's OWN Dialog.Overlay legitimately renders those
  // literal tokens while open). Instead assert the dialog is Radix-rendered
  // (stamped `data-state`, closable via Escape/outside-click) rather than the
  // old hand-rolled `<div role="dialog">` that carried none of that.
  it('renders through Radix Dialog (FormDialog), not a hand-rolled overlay div (DOCK-9)', () => {
    render(<GenerateSchemaDialog projectId="p1" onClose={vi.fn()} onAdopt={vi.fn()} />);
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('data-state', 'open');
    expect(screen.queryByTestId('generate-schema-dialog')).not.toBeInTheDocument();
  });

  it('calls onClose when the dialog requests to close (Radix onOpenChange)', () => {
    const onClose = vi.fn();
    render(<GenerateSchemaDialog projectId="p1" onClose={onClose} onAdopt={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /close/i }));
    expect(onClose).toHaveBeenCalled();
  });

  it('generates then adopts only the ticked components', async () => {
    proposeMock.mockResolvedValue({
      node_kinds: [{ code: 'character' }, { code: 'sect' }],
      edge_types: [{ code: 'MENTOR_OF', source_kinds: ['character'], target_kinds: ['character'] }],
      fact_types: [{ code: 'ascension' }],
    });
    const onAdopt = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();
    render(<GenerateSchemaDialog projectId="p1" onClose={onClose} onAdopt={onAdopt} />);

    // Generate is gated on premise + a model
    fireEvent.change(screen.getByTestId('generate-premise'), { target: { value: 'a xianxia tale' } });
    fireEvent.click(screen.getByTestId('pick-model'));
    fireEvent.click(screen.getByTestId('generate-run'));
    await waitFor(() => expect(screen.getByTestId('generate-adopt')).toBeInTheDocument());
    expect(proposeMock).toHaveBeenCalledWith({ premise: 'a xianxia tale', genre: undefined, model_ref: 'm1' });

    // untick 'sect' → it should NOT be adopted
    fireEvent.click(screen.getByTestId('generate-pick-k-sect'));
    fireEvent.click(screen.getByTestId('generate-adopt'));

    await waitFor(() => expect(onAdopt).toHaveBeenCalled());
    const picks = onAdopt.mock.calls[0][0];
    expect(picks.kinds.map((k: { code: string }) => k.code)).toEqual(['character']); // sect unticked
    expect(picks.edges.map((e: { code: string }) => e.code)).toEqual(['MENTOR_OF']);
    expect(picks.facts.map((f: { code: string }) => f.code)).toEqual(['ascension']);
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('gates Generate until a premise and model are set', () => {
    render(<GenerateSchemaDialog projectId="p1" onClose={vi.fn()} onAdopt={vi.fn()} />);
    expect(screen.getByTestId('generate-run')).toBeDisabled();
    fireEvent.change(screen.getByTestId('generate-premise'), { target: { value: 'x' } });
    expect(screen.getByTestId('generate-run')).toBeDisabled(); // still no model
    fireEvent.click(screen.getByTestId('pick-model'));
    expect(screen.getByTestId('generate-run')).not.toBeDisabled();
  });
});
