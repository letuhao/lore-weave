import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ToolCallIndicator } from '../ToolCallIndicator';
import type { ToolCallRecord } from '../../types';

// K21-C (D2): the tool-call indicator chip row + expand detail.

describe('ToolCallIndicator', () => {
  it('renders nothing when toolCalls is empty', () => {
    const { container } = render(<ToolCallIndicator toolCalls={[]} />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId('tool-call-indicator')).toBeNull();
  });

  it('renders a chip per tool call with the spec label', () => {
    const calls: ToolCallRecord[] = [
      { tool: 'memory_search', ok: true },
      { tool: 'memory_remember', ok: true },
    ];
    render(<ToolCallIndicator toolCalls={calls} />);
    const chips = screen.getAllByTestId('tool-call-chip');
    expect(chips).toHaveLength(2);
    expect(chips[0]).toHaveTextContent('Searched memory');
    expect(chips[1]).toHaveTextContent('Noted a memory');
  });

  it('maps every known tool name to its label', () => {
    const calls: ToolCallRecord[] = [
      { tool: 'memory_search', ok: true },
      { tool: 'memory_recall_entity', ok: true },
      { tool: 'memory_timeline', ok: true },
      { tool: 'memory_remember', ok: true },
      { tool: 'memory_forget', ok: true },
    ];
    render(<ToolCallIndicator toolCalls={calls} />);
    const chips = screen.getAllByTestId('tool-call-chip');
    expect(chips[0]).toHaveTextContent('Searched memory');
    expect(chips[1]).toHaveTextContent('Recalled an entity');
    expect(chips[2]).toHaveTextContent('Checked the timeline');
    expect(chips[3]).toHaveTextContent('Noted a memory');
    expect(chips[4]).toHaveTextContent('Forgot a fact');
  });

  it('falls back to the raw tool name for an unknown tool', () => {
    render(<ToolCallIndicator toolCalls={[{ tool: 'memory_future', ok: true }]} />);
    expect(screen.getByTestId('tool-call-chip')).toHaveTextContent('memory_future');
  });

  it('detail list is hidden until the row is clicked, then toggles', () => {
    render(<ToolCallIndicator toolCalls={[{ tool: 'memory_search', ok: true }]} />);
    expect(screen.queryByTestId('tool-call-detail')).toBeNull();

    const rowBtn = screen.getByTestId('tool-call-indicator').querySelector('button')!;
    fireEvent.click(rowBtn);
    expect(screen.getByTestId('tool-call-detail')).toBeInTheDocument();

    fireEvent.click(rowBtn);
    expect(screen.queryByTestId('tool-call-detail')).toBeNull();
  });

  it('detail row shows ok / failed per call and the iteration when known', () => {
    const calls: ToolCallRecord[] = [
      { tool: 'memory_search', ok: true, iteration: 1 },
      { tool: 'memory_remember', ok: false },
    ];
    render(<ToolCallIndicator toolCalls={calls} />);
    fireEvent.click(screen.getByTestId('tool-call-indicator').querySelector('button')!);
    const detail = screen.getByTestId('tool-call-detail');
    expect(detail).toHaveTextContent('ok');
    expect(detail).toHaveTextContent('failed');
    expect(detail).toHaveTextContent('step 1');
  });

  it('marks a failed call with aria-expanded toggling on the row button', () => {
    render(<ToolCallIndicator toolCalls={[{ tool: 'memory_forget', ok: false }]} />);
    const btn = screen.getByTestId('tool-call-indicator').querySelector('button')!;
    expect(btn).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(btn);
    expect(btn).toHaveAttribute('aria-expanded', 'true');
  });
});
