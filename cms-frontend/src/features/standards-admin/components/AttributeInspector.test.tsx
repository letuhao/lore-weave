import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { AttributeInspector } from './AttributeInspector';
import type { SystemAttribute } from '../types';

function attr(over: Partial<SystemAttribute>): SystemAttribute {
  return {
    attr_id: 'a1',
    kind_id: 'k1',
    genre_id: 'g1',
    code: 'role',
    name: 'Role',
    description: 'The role played',
    field_type: 'text',
    is_required: false,
    sort_order: 3,
    options: null,
    ...over,
  };
}

describe('AttributeInspector', () => {
  it('shows a placeholder when no attribute is selected', () => {
    render(<AttributeInspector attribute={null} />);
    expect(screen.getByText(/select an attribute/i)).toBeInTheDocument();
  });

  it('renders code, name, field-type badge, description, required and sort', () => {
    render(<AttributeInspector attribute={attr({ is_required: true })} />);
    expect(screen.getByText('role')).toBeInTheDocument();
    expect(screen.getByText('Role')).toBeInTheDocument();
    expect(screen.getByText('text')).toBeInTheDocument();
    expect(screen.getByText('The role played')).toBeInTheDocument();
    expect(screen.getByText(/required: yes/i)).toBeInTheDocument();
    expect(screen.getByText(/sort: 3/i)).toBeInTheDocument();
  });

  it('renders options chips ONLY when field_type is select', () => {
    const { rerender } = render(
      <AttributeInspector attribute={attr({ field_type: 'select', options: ['hero', 'villain'] })} />,
    );
    expect(screen.getByText('hero')).toBeInTheDocument();
    expect(screen.getByText('villain')).toBeInTheDocument();

    // A tags attribute carrying options must NOT render the chips (select-only).
    rerender(
      <AttributeInspector attribute={attr({ field_type: 'tags', options: ['hero', 'villain'] })} />,
    );
    expect(screen.queryByText('hero')).toBeNull();
    expect(screen.queryByText('villain')).toBeNull();
  });
});
