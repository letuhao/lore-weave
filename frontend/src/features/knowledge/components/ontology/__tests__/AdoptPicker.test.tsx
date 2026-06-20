import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AdoptPicker } from '../AdoptPicker';
import type { GraphSchemaSummary, NeedsGlossary } from '../../../types/ontology';

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
});
