import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { StyleVoicePanel } from '../StyleVoicePanel';

const h = vi.hoisted(() => ({
  setStyle: vi.fn(),
  setVoice: vi.fn(),
  delVoice: vi.fn(),
  styleData: [] as any[],
  voiceData: [] as any[],
  castData: [] as any[],
}));
vi.mock('../../hooks/useStyleVoice', () => ({
  useStyleProfiles: () => ({ data: h.styleData }),
  useSetStyleProfile: () => ({ mutate: h.setStyle }),
  useVoiceProfiles: () => ({ data: h.voiceData }),
  useSetVoiceProfile: () => ({ mutate: h.setVoice }),
  useDeleteVoiceProfile: () => ({ mutate: h.delVoice }),
}));
vi.mock('../../hooks/useCast', () => ({
  useCast: () => ({ entities: { data: h.castData } }),
}));

beforeEach(() => {
  h.setStyle.mockReset(); h.setVoice.mockReset(); h.delVoice.mockReset();
  h.styleData = []; h.voiceData = []; h.castData = [];
});

const renderPanel = (over = {}) =>
  render(<StyleVoicePanel projectId="p1" token="t" chapterId="c1" sceneId="s1" {...over} />);

describe('StyleVoicePanel (T3.5)', () => {
  it('commits density/pace for the active scope on slider release', () => {
    renderPanel();
    fireEvent.change(screen.getByTestId('style-density'), { target: { value: '80' } });
    fireEvent.pointerUp(screen.getByTestId('style-density'));
    expect(h.setStyle).toHaveBeenCalledWith({ scope_type: 'work', scope_id: 'p1', density: 80, pace: 50 });
  });

  it('switches scope so the slider commits to the chapter scope_id', () => {
    renderPanel();
    fireEvent.click(screen.getByTestId('style-scope-chapter'));
    fireEvent.change(screen.getByTestId('style-pace'), { target: { value: '70' } });
    fireEvent.pointerUp(screen.getByTestId('style-pace'));
    expect(h.setStyle).toHaveBeenCalledWith({ scope_type: 'chapter', scope_id: 'c1', density: 50, pace: 70 });
  });

  it('disables the scene scope button when there is no sceneId', () => {
    renderPanel({ sceneId: undefined });
    expect(screen.getByTestId('style-scope-scene')).toBeDisabled();
  });

  it('renders existing voice rows and adds a tag on Enter', () => {
    h.voiceData = [{ entity_id: 'e1', entity_name: 'Kael', tags: ['terse'] }];
    renderPanel();
    expect(screen.getByTestId('voice-row-e1')).toBeInTheDocument();
    const input = screen.getByTestId('voice-tag-input-e1');
    fireEvent.change(input, { target: { value: 'wry' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(h.setVoice).toHaveBeenCalledWith({ entity_id: 'e1', entity_name: 'Kael', tags: ['terse', 'wry'] });
  });

  it('does not add a duplicate tag', () => {
    h.voiceData = [{ entity_id: 'e1', entity_name: 'Kael', tags: ['terse'] }];
    renderPanel();
    const input = screen.getByTestId('voice-tag-input-e1');
    fireEvent.change(input, { target: { value: 'terse' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(h.setVoice).not.toHaveBeenCalled();
  });

  it('adds a new character voice from the cast search', () => {
    // knowledge entity-list items key on `id` (the producer schema), not `entity_id`
    h.castData = [{ id: 'e2', canonical_name: 'Mira' }];
    renderPanel();
    fireEvent.change(screen.getByTestId('voice-search'), { target: { value: 'Mi' } });
    fireEvent.click(screen.getByTestId('voice-add-e2'));
    expect(h.setVoice).toHaveBeenCalledWith({ entity_id: 'e2', entity_name: 'Mira', tags: [] });
  });

  it('removes a voice profile', () => {
    h.voiceData = [{ entity_id: 'e1', entity_name: 'Kael', tags: [] }];
    renderPanel();
    fireEvent.click(screen.getByTestId('voice-remove-e1'));
    expect(h.delVoice).toHaveBeenCalledWith('e1');
  });
});
