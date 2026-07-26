import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AdoptPicker } from '../AdoptPicker';
import type {
  AdoptLoss,
  GraphSchemaSummary,
  NeedsGlossary,
} from '../../../types/ontology';

const SCHEMAS: GraphSchemaSummary[] = [
  { schema_id: 's1', scope: 'system', code: 'xianxia-harem', name: 'Xianxia Harem', schema_version: 1, allow_free_edges: false },
  { schema_id: 's2', scope: 'user', code: 'my-mystery', name: 'My Mystery', schema_version: 2, allow_free_edges: true },
];

function renderPicker(over: Partial<React.ComponentProps<typeof AdoptPicker>> = {}) {
  const props = {
    schemas: SCHEMAS,
    selectedId: null,
    onSelect: vi.fn(),
    onAdopt: vi.fn(),
    isAdopting: false,
    needsGlossary: null as NeedsGlossary | null,
    onOpenGlossary: vi.fn(),
    onClearGate: vi.fn(),
    wouldLose: [] as AdoptLoss[],
    lossBlocked: false,
    onAcknowledgeLoss: vi.fn(),
    ...over,
  };
  render(<AdoptPicker {...props} />);
  return props;
}

describe('AdoptPicker', () => {
  it('lists templates and fires onSelect', () => {
    const props = renderPicker();
    fireEvent.click(screen.getByTestId('adopt-template-xianxia-harem'));
    expect(props.onSelect).toHaveBeenCalledWith('s1');
  });

  it('disables adopt until a template is selected', () => {
    renderPicker({ selectedId: null });
    expect(screen.getByTestId('adopt-submit')).toBeDisabled();
  });

  it('enables adopt and fires onAdopt with the selected id', () => {
    const props = renderPicker({ selectedId: 's2' });
    const btn = screen.getByTestId('adopt-submit');
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);
    expect(props.onAdopt).toHaveBeenCalledWith('s2');
  });

  it('renders the M1 needs_glossary blocker, blocks adopt, and deep-links', () => {
    const needsGlossary: NeedsGlossary = {
      code: 'KG_ADOPT_NEEDS_GLOSSARY',
      message: 'missing',
      needs_glossary: { book_id: 'b1', kinds: ['concept', 'technique'] },
    };
    const props = renderPicker({ selectedId: 's1', needsGlossary });

    expect(screen.getByTestId('adopt-needs-glossary')).toBeInTheDocument();
    expect(screen.getByText('concept')).toBeInTheDocument();
    expect(screen.getByText('technique')).toBeInTheDocument();
    // adopt is blocked while the gate is up
    expect(screen.getByTestId('adopt-submit')).toBeDisabled();

    fireEvent.click(screen.getByTestId('adopt-open-glossary'));
    expect(props.onOpenGlossary).toHaveBeenCalledWith('b1');
  });

  // ── re-adopt loss preview (D-KG-LC-REVADOPT-LOSS) ──
  const LOSSES: AdoptLoss[] = [
    { node_type: 'edge_type', code: 'MY_CUSTOM_EDGE', change: 'removed_upstream' },
    { node_type: 'fact_type', code: 'ascension', change: 'modified', fields_changed: ['label'] },
  ];

  it('renders the loss warning and lists the customizations that would be lost', () => {
    renderPicker({ selectedId: 's1', wouldLose: LOSSES, lossBlocked: true });
    expect(screen.getByTestId('adopt-loss-warning')).toBeInTheDocument();
    expect(screen.getByText('MY_CUSTOM_EDGE')).toBeInTheDocument();
    expect(screen.getByText('ascension')).toBeInTheDocument();
  });

  it('blocks adopt until the loss warning is acknowledged', () => {
    renderPicker({ selectedId: 's1', wouldLose: LOSSES, lossBlocked: true });
    expect(screen.getByTestId('adopt-submit')).toBeDisabled();
  });

  it('fires onAcknowledgeLoss from the proceed gate', () => {
    const props = renderPicker({
      selectedId: 's1',
      wouldLose: LOSSES,
      lossBlocked: true,
    });
    fireEvent.click(screen.getByTestId('adopt-loss-acknowledge'));
    expect(props.onAcknowledgeLoss).toHaveBeenCalled();
  });

  it('enables adopt once the loss is acknowledged (lossBlocked=false)', () => {
    renderPicker({ selectedId: 's1', wouldLose: LOSSES, lossBlocked: false });
    // warning still visible (still has losses) but adopt is allowed.
    expect(screen.getByTestId('adopt-loss-warning')).toBeInTheDocument();
    expect(screen.getByTestId('adopt-submit')).not.toBeDisabled();
  });

  it('shows no loss warning when there are no losses', () => {
    renderPicker({ selectedId: 's1', wouldLose: [] });
    expect(screen.queryByTestId('adopt-loss-warning')).not.toBeInTheDocument();
    expect(screen.getByTestId('adopt-submit')).not.toBeDisabled();
  });

  it('prioritizes the glossary gate over the loss warning', () => {
    const needsGlossary: NeedsGlossary = {
      code: 'KG_ADOPT_NEEDS_GLOSSARY',
      message: 'missing',
      needs_glossary: { book_id: 'b1', kinds: ['concept'] },
    };
    renderPicker({
      selectedId: 's1',
      needsGlossary,
      wouldLose: LOSSES,
      lossBlocked: true,
    });
    // glossary blocker wins — loss warning is suppressed while it's up.
    expect(screen.getByTestId('adopt-needs-glossary')).toBeInTheDocument();
    expect(screen.queryByTestId('adopt-loss-warning')).not.toBeInTheDocument();
    expect(screen.getByTestId('adopt-submit')).toBeDisabled();
  });
});
