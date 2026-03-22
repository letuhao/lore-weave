import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { TagEditor } from './TagEditor';
import { ModelTag } from '@/features/ai-models/api';

const initialTags: ModelTag[] = [
  { tag_name: 'tts', note: 'text to speech' },
  { tag_name: 'thinking', note: 'chain-of-thought' },
];

const renderEditor = (tags: ModelTag[], onChange = vi.fn(), disabled = false) =>
  render(<TagEditor tags={tags} onChange={onChange} disabled={disabled} />);

describe('TagEditor — chip display', () => {
  beforeEach(() => { cleanup(); });

  it('T1: renders existing tags as chips with tag_name and note', () => {
    renderEditor(initialTags);
    expect(screen.getByText('tts')).toBeInTheDocument();
    expect(screen.getByText('text to speech')).toBeInTheDocument();
    expect(screen.getByText('thinking')).toBeInTheDocument();
    expect(screen.getByText('chain-of-thought')).toBeInTheDocument();
  });

  it('T2: chip with empty note only shows tag_name and × button — no italic note span', () => {
    const { container } = renderEditor([{ tag_name: 'chat', note: '' }]);
    expect(screen.getByText('chat')).toBeInTheDocument();
    // no italic note span should be rendered
    expect(container.querySelector('span.italic')).toBeNull();
    // only one × button
    expect(screen.getAllByRole('button', { name: /Remove/i })).toHaveLength(1);
  });
});

describe('TagEditor — add tag', () => {
  beforeEach(() => { cleanup(); });

  it('T3: clicking [+ Add tag] shows add form with name and note inputs', () => {
    renderEditor([]);
    fireEvent.click(screen.getByRole('button', { name: '+ Add tag' }));
    expect(screen.getByPlaceholderText('Tag name *')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Note (optional)')).toBeInTheDocument();
  });

  it('T4: clicking [+ Add tag] again hides the add form', () => {
    renderEditor([]);
    fireEvent.click(screen.getByRole('button', { name: '+ Add tag' }));
    fireEvent.click(screen.getByRole('button', { name: '+ Add tag' }));
    expect(screen.queryByPlaceholderText('Tag name *')).not.toBeInTheDocument();
  });

  it('T5: fill name + click Add → onChange called with new tag appended', () => {
    const onChange = vi.fn();
    renderEditor([{ tag_name: 'chat', note: '' }], onChange);
    fireEvent.click(screen.getByRole('button', { name: '+ Add tag' }));
    fireEvent.change(screen.getByPlaceholderText('Tag name *'), { target: { value: 'vision' } });
    fireEvent.change(screen.getByPlaceholderText('Note (optional)'), { target: { value: 'image input' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(onChange).toHaveBeenCalledOnce();
    const result: ModelTag[] = onChange.mock.calls[0][0];
    expect(result.some((t) => t.tag_name === 'vision' && t.note === 'image input')).toBe(true);
  });

  it('T6: tags are sorted alphabetically (case-insensitive) after Add', () => {
    const onChange = vi.fn();
    renderEditor([{ tag_name: 'Zebra', note: '' }], onChange);
    fireEvent.click(screen.getByRole('button', { name: '+ Add tag' }));
    fireEvent.change(screen.getByPlaceholderText('Tag name *'), { target: { value: 'apple' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    const result: ModelTag[] = onChange.mock.calls[0][0];
    expect(result[0].tag_name.toLowerCase()).toBe('apple');
    expect(result[1].tag_name.toLowerCase()).toBe('zebra');
  });

  it('T7: empty tag name → Add button disabled', () => {
    renderEditor([]);
    fireEvent.click(screen.getByRole('button', { name: '+ Add tag' }));
    // name is empty by default
    expect(screen.getByRole('button', { name: 'Add' })).toBeDisabled();
  });

  it('T8: duplicate tag name → error shown and Add button disabled', () => {
    renderEditor([{ tag_name: 'chat', note: '' }]);
    fireEvent.click(screen.getByRole('button', { name: '+ Add tag' }));
    fireEvent.change(screen.getByPlaceholderText('Tag name *'), { target: { value: 'chat' } });
    expect(screen.getByText('Tag name already exists')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add' })).toBeDisabled();
  });

  it('T9: click Cancel on add form → form closes, onChange NOT called', () => {
    const onChange = vi.fn();
    renderEditor([], onChange);
    fireEvent.click(screen.getByRole('button', { name: '+ Add tag' }));
    fireEvent.change(screen.getByPlaceholderText('Tag name *'), { target: { value: 'vision' } });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByPlaceholderText('Tag name *')).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe('TagEditor — edit tag', () => {
  beforeEach(() => { cleanup(); });

  it('T10: clicking a chip enters edit mode pre-filled with current values', () => {
    renderEditor([{ tag_name: 'tts', note: 'text to speech' }]);
    fireEvent.click(screen.getByRole('button', { name: 'tts' }));
    expect(screen.getByDisplayValue('tts')).toBeInTheDocument();
    expect(screen.getByDisplayValue('text to speech')).toBeInTheDocument();
  });

  it('T11: edit name + click Save → onChange called with updated tag and re-sorted', () => {
    const onChange = vi.fn();
    renderEditor(
      [{ tag_name: 'zzz', note: '' }, { tag_name: 'aaa', note: '' }],
      onChange,
    );
    // click 'zzz' chip to edit it
    fireEvent.click(screen.getByRole('button', { name: 'zzz' }));
    fireEvent.change(screen.getByDisplayValue('zzz'), { target: { value: 'mmm' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    const result: ModelTag[] = onChange.mock.calls[0][0];
    expect(result[0].tag_name).toBe('aaa');
    expect(result[1].tag_name).toBe('mmm');
  });

  it('T12: edit to duplicate name → error shown, Save disabled', () => {
    renderEditor([{ tag_name: 'chat', note: '' }, { tag_name: 'vision', note: '' }]);
    fireEvent.click(screen.getByRole('button', { name: 'chat' }));
    // change to duplicate name
    const nameInput = screen.getByDisplayValue('chat');
    fireEvent.change(nameInput, { target: { value: 'vision' } });
    expect(screen.getByText('Tag name already exists')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  });

  it('T13: edit to empty name → Save button disabled', () => {
    renderEditor([{ tag_name: 'chat', note: '' }]);
    fireEvent.click(screen.getByRole('button', { name: 'chat' }));
    fireEvent.change(screen.getByDisplayValue('chat'), { target: { value: '' } });
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  });

  it('T14: click Cancel in edit mode → form closes, onChange NOT called', () => {
    const onChange = vi.fn();
    renderEditor([{ tag_name: 'chat', note: '' }], onChange);
    fireEvent.click(screen.getByRole('button', { name: 'chat' }));
    fireEvent.change(screen.getByDisplayValue('chat'), { target: { value: 'changed' } });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onChange).not.toHaveBeenCalled();
    // original chip restored
    expect(screen.getByRole('button', { name: 'chat' })).toBeInTheDocument();
  });
});

describe('TagEditor — remove tag', () => {
  beforeEach(() => { cleanup(); });

  it('T15: click × on a chip → onChange called with that tag removed', () => {
    const onChange = vi.fn();
    renderEditor([{ tag_name: 'chat', note: '' }, { tag_name: 'vision', note: '' }], onChange);
    fireEvent.click(screen.getByRole('button', { name: 'Remove chat' }));
    const result: ModelTag[] = onChange.mock.calls[0][0];
    expect(result).toHaveLength(1);
    expect(result[0].tag_name).toBe('vision');
  });
});

describe('TagEditor — disabled', () => {
  beforeEach(() => { cleanup(); });

  it('T16: disabled=true → all buttons and inputs are disabled', () => {
    renderEditor([{ tag_name: 'chat', note: '' }], vi.fn(), true);
    expect(screen.getByRole('button', { name: '+ Add tag' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Remove chat' })).toBeDisabled();
    // chip button (edit trigger)
    expect(screen.getByRole('button', { name: 'chat' })).toBeDisabled();
  });
});
