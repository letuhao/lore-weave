import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CastEntityRow } from '../CastEntityRow';
import type { CastRow } from '../../hooks/useCast';

const { detailHook, eventsHook, factsHook, navigateFn } = vi.hoisted(() => ({
  detailHook: vi.fn(), eventsHook: vi.fn(), factsHook: vi.fn(), navigateFn: vi.fn(),
}));
vi.mock('../../hooks/useCast', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../hooks/useCast');
  return {
    ...actual,
    useEntityDetail: () => detailHook(),
    useEntityEvents: () => eventsHook(),
    useEntityFacts: () => factsHook(),
  };
});
vi.mock('react-router-dom', () => ({ useNavigate: () => navigateFn }));

const ROW: CastRow = {
  id: 'e1', user_id: 'u', project_id: 'p', name: 'Kai', canonical_name: 'kai',
  kind: 'character', aliases: [], canonical_version: 1, source_types: [], confidence: 0.9,
  glossary_entity_id: null, anchor_score: 0, archived_at: null, archive_reason: null,
  evidence_count: 1, mention_count: 1, user_edited: false, version: 5,
  created_at: null, updated_at: null, state: undefined,
};

describe('CastEntityRow — additive edit props (DP-3)', () => {
  beforeEach(() => {
    detailHook.mockReturnValue({ data: { relations: [], total_relations: 0 } });
    eventsHook.mockReturnValue({ data: [] });
    factsHook.mockReturnValue({ data: { facts: [] } });
  });

  it('legacy mount (no edit props) shows NO edit UI', () => {
    render(<CastEntityRow row={ROW} bookId="b" chapterId="c" token="t" />);
    expect(screen.queryByTestId('cast-row-rename')).toBeNull();
    expect(screen.queryByTestId('cast-row-edit')).toBeNull();
    expect(screen.queryByTestId('cast-row-archive')).toBeNull();
  });

  it('dock mount renders rename/edit/archive affordances', () => {
    render(
      <CastEntityRow
        row={ROW} bookId="b" chapterId="c" token="t"
        onRename={vi.fn()} onEdit={vi.fn()} onArchive={vi.fn()}
      />,
    );
    expect(screen.getByTestId('cast-row-rename')).toBeTruthy();
    expect(screen.getByTestId('cast-row-edit')).toBeTruthy();
    expect(screen.getByTestId('cast-row-archive')).toBeTruthy();
  });

  it('inline rename commits {entityId, name, version} on Enter', () => {
    const onRename = vi.fn();
    render(
      <CastEntityRow row={ROW} bookId="b" chapterId="c" token="t" onRename={onRename} />,
    );
    fireEvent.click(screen.getByTestId('cast-row-rename'));
    const input = screen.getByTestId('cast-row-rename-input');
    fireEvent.change(input, { target: { value: 'Kai the Brave' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onRename).toHaveBeenCalledWith({
      entityId: 'e1', name: 'Kai the Brave', version: 5,
    });
  });

  it('inline rename does NOT fire when the name is unchanged (no false write)', () => {
    const onRename = vi.fn();
    render(
      <CastEntityRow row={ROW} bookId="b" chapterId="c" token="t" onRename={onRename} />,
    );
    fireEvent.click(screen.getByTestId('cast-row-rename'));
    const input = screen.getByTestId('cast-row-rename-input');
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onRename).not.toHaveBeenCalled();
  });
});
