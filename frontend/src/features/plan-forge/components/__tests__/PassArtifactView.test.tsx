import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { PassArtifactView } from '../PassArtifactView';

describe('PassArtifactView (F-1 — readable per-kind render, not raw JSON)', () => {
  it('cast_plan → a roster list of name/role/trait', () => {
    render(<PassArtifactView kind="cast_plan" content={{ cast: [
      { name: 'Diệp Vấn Vũ', role: 'protagonist', trait: 'the discarded fifth miss' },
    ] }} />);
    const el = screen.getByTestId('artifact-cast');
    expect(el.textContent).toContain('Diệp Vấn Vũ');
    expect(el.textContent).toContain('protagonist');
    expect(el.textContent).toContain('the discarded fifth miss');
    expect(screen.queryByTestId('artifact-json')).toBeNull(); // NOT raw JSON
  });

  it('cast_plan tolerates the `roster` key too', () => {
    render(<PassArtifactView kind="cast_plan" content={{ roster: [{ name: 'Bạch Sư' }] }} />);
    expect(screen.getByTestId('artifact-cast').textContent).toContain('Bạch Sư');
  });

  it('beat_plan → an ordered beat list', () => {
    render(<PassArtifactView kind="beat_plan" content={{ beats: [
      { beat: 'inciting', tension: 30, synopsis: 'the root is severed' },
    ] }} />);
    const el = screen.getByTestId('artifact-beats');
    expect(el.textContent).toContain('inciting');
    expect(el.textContent).toContain('the root is severed');
  });

  it('an unknown kind falls back to formatted JSON (never blank)', () => {
    render(<PassArtifactView kind="world_plan" content={{ regions: 3 }} />);
    expect(screen.getByTestId('artifact-json').textContent).toContain('regions');
  });

  it('an empty cast renders a friendly note, not a crash', () => {
    render(<PassArtifactView kind="cast_plan" content={{ cast: [] }} />);
    expect(screen.queryByTestId('artifact-cast')).toBeNull();
    expect(screen.getByText(/No cast members/)).toBeInTheDocument();
  });
});
