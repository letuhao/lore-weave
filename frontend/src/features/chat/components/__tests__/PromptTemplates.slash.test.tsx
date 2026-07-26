// D-REG-P4-SLASH-AUTOCOMPLETE — the `/` picker now surfaces the user's REGISTRY
// commands above the built-in templates. EFFECT: a command row renders + selecting it
// fires onSelectCommand (which completes the `/name ` token), and Enter picks the first
// row (a command, not a template).
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import type { SlashCommandItem } from '../../hooks/useSlashCommands';

const cmds: SlashCommandItem[] = [
  { command_id: 'c1', name: 'plan-scene', description: 'Plan a scene' },
  { command_id: 'c2', name: 'plot-check', description: 'Check plot holes' },
];
// The picker owns the command source; mock the hook so these stay pure/deterministic.
const match = vi.hoisted(() => vi.fn());
vi.mock('../../hooks/useSlashCommands', () => ({ useSlashCommands: () => ({ commands: [], match }) }));

import { PromptTemplatePicker } from '../PromptTemplates';

describe('PromptTemplatePicker — registry commands', () => {
  it('renders the user commands section above templates', () => {
    match.mockReturnValue(cmds);
    render(<PromptTemplatePicker open filter="pl" onSelect={() => {}} onSelectCommand={() => {}} onClose={() => {}} />);
    const items = screen.getAllByTestId('slash-command-item');
    expect(items.map((i) => i.textContent)).toEqual(expect.arrayContaining([expect.stringContaining('/plan-scene')]));
    expect(screen.getByText('Your commands')).toBeTruthy();
  });

  it('clicking a command fires onSelectCommand (completes the token), not onSelect', () => {
    match.mockReturnValue(cmds);
    const onSelectCommand = vi.fn();
    const onSelect = vi.fn();
    render(<PromptTemplatePicker open filter="" onSelect={onSelect} onSelectCommand={onSelectCommand} onClose={() => {}} />);
    fireEvent.click(screen.getAllByTestId('slash-command-item')[0]);
    expect(onSelectCommand).toHaveBeenCalledWith(cmds[0]);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('Enter selects the first row (a command when commands are present)', () => {
    match.mockReturnValue(cmds);
    const onSelectCommand = vi.fn();
    render(<PromptTemplatePicker open filter="" onSelect={() => {}} onSelectCommand={onSelectCommand} onClose={() => {}} />);
    fireEvent.keyDown(window, { key: 'Enter' });
    expect(onSelectCommand).toHaveBeenCalledWith(cmds[0]);
  });

  it('with no commands, behaves as the classic template picker (Escape closes)', () => {
    match.mockReturnValue([]);
    const onClose = vi.fn();
    render(<PromptTemplatePicker open filter="" onSelect={() => {}} onSelectCommand={() => {}} onClose={onClose} />);
    expect(screen.queryByText('Your commands')).toBeNull();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });
});
