import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { BindingSettings } from '../BindingSettings';
import type { Mode, ModeBinding } from '../../types';

const binding = (mode: Mode, over: Partial<ModeBinding> = {}): ModeBinding => ({
  mode,
  inject_skills: [],
  inject_workflows: [],
  seed_tool_categories: [],
  disable_workflows: [],
  ...over,
});

const empty = { ask: binding('ask'), write: binding('write'), plan: binding('plan') };

describe('BindingSettings (M6 — presentational)', () => {
  it('tags each effective workflow with the TIER it came from (SET-1: effective + source)', () => {
    const bindings = {
      ...empty,
      write: binding('write', {
        inject_workflows: ['vision-to-book', 'my-own'],
        sources: {
          system: { tier: 'system', inject_skills: [], inject_workflows: ['vision-to-book'], seed_tool_categories: [], disable_workflows: [] },
          user: { tier: 'user', inject_skills: [], inject_workflows: ['my-own'], seed_tool_categories: [], disable_workflows: [] },
        },
      }),
    };
    render(<BindingSettings bindings={bindings} loading={false} error={null} busyMode={null} onToggleDisabled={vi.fn()} />);

    // both workflows render under the Writing mode, each with its source-tier badge
    expect(screen.getByTestId('binding-write-vision-to-book')).toHaveTextContent('Built-in');
    expect(screen.getByTestId('binding-write-my-own')).toHaveTextContent('You set this');
  });

  it('turning off a System pin calls onToggleDisabled(mode, slug, true) — the veto', () => {
    const onToggle = vi.fn();
    const bindings = { ...empty, write: binding('write', { inject_workflows: ['vision-to-book'], sources: { system: { tier: 'system', inject_skills: [], inject_workflows: ['vision-to-book'], seed_tool_categories: [], disable_workflows: [] } } }) };
    render(<BindingSettings bindings={bindings} loading={false} error={null} busyMode={null} onToggleDisabled={onToggle} />);
    fireEvent.click(screen.getByTestId('binding-write-vision-to-book-disable'));
    expect(onToggle).toHaveBeenCalledWith('write', 'vision-to-book', true);
  });

  it('a vetoed workflow shows struck-through with a re-enable that calls onToggleDisabled(..., false)', () => {
    const onToggle = vi.fn();
    const bindings = { ...empty, write: binding('write', { inject_workflows: [], disable_workflows: ['vision-to-book'] }) };
    render(<BindingSettings bindings={bindings} loading={false} error={null} busyMode={null} onToggleDisabled={onToggle} />);
    const off = screen.getByTestId('binding-write-vision-to-book-off');
    expect(off).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('binding-write-vision-to-book-enable'));
    expect(onToggle).toHaveBeenCalledWith('write', 'vision-to-book', false);
  });

  it('disables the buttons for a mode while it is busy (no double-submit)', () => {
    const bindings = { ...empty, write: binding('write', { inject_workflows: ['x'], sources: { system: { tier: 'system', inject_skills: [], inject_workflows: ['x'], seed_tool_categories: [], disable_workflows: [] } } }) };
    render(<BindingSettings bindings={bindings} loading={false} error={null} busyMode="write" onToggleDisabled={vi.fn()} />);
    expect(screen.getByTestId('binding-write-x-disable')).toBeDisabled();
  });

  it('shows loading and error states', () => {
    const { rerender } = render(<BindingSettings bindings={empty} loading error={null} busyMode={null} onToggleDisabled={vi.fn()} />);
    expect(screen.getByTestId('bindings-loading')).toBeInTheDocument();
    rerender(<BindingSettings bindings={empty} loading={false} error="boom" busyMode={null} onToggleDisabled={vi.fn()} />);
    expect(screen.getByTestId('bindings-error')).toHaveTextContent('boom');
  });
});
