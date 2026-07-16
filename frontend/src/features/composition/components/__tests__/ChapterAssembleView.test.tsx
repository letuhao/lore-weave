import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ChapterAssembleView } from '../ChapterAssembleView';

// vi.hoisted: vi.mock factories hoist above top-level consts.
const { mockGen, mockStitch, mockSetMode, mockCorrection } = vi.hoisted(() => ({
  mockGen: { mutate: vi.fn(), isPending: false, error: null as unknown },
  mockStitch: { mutate: vi.fn(), isPending: false, error: null as unknown },
  mockSetMode: { mutate: vi.fn(), isPending: false },
  mockCorrection: { mutate: vi.fn(), isPending: false },
}));
vi.mock('../../hooks/useChapterAssembly', () => ({
  useGenerateChapter: () => mockGen,
  useStitchChapter: () => mockStitch,
  useSetAssemblyMode: () => mockSetMode,
}));
vi.mock('../../hooks/useAutoGenerate', () => ({ useCorrection: () => mockCorrection }));

const CHAPTER_RESULT = { job_id: 'job-ch', status: 'completed', text: 'CH PROSE', assembly_mode: 'chapter' as const };
const STITCH_RESULT = {
  job_id: 'job-st', status: 'completed', text: 'ST PROSE',
  assembly_mode: 'per_scene_stitch' as const, stitched: false, degraded: true,
};

beforeEach(() => {
  // fresh fns each test (clearAllMocks keeps stale implementations otherwise).
  mockGen.mutate = vi.fn(); mockGen.isPending = false; mockGen.error = null;
  mockStitch.mutate = vi.fn(); mockStitch.isPending = false; mockStitch.error = null;
  mockSetMode.mutate = vi.fn();
  mockCorrection.mutate = vi.fn();
});

const base = {
  projectId: 'p', bookId: 'b', chapterId: 'c', modelRef: 'm',
  settings: {} as Record<string, unknown>, scenesAllDone: true, token: 'tok',
};

const preview = () => screen.getByTestId('assemble-preview') as HTMLTextAreaElement;
const btn = (id: string) => screen.getByTestId(id) as HTMLButtonElement;

describe('ChapterAssembleView (B-FE chapter-assembly)', () => {
  it('Generate chapter calls the chapter endpoint and shows the editable result', () => {
    mockGen.mutate.mockImplementation((_p, opts) => opts?.onSuccess?.(CHAPTER_RESULT));
    render(<ChapterAssembleView {...base} onAccept={vi.fn()} />);
    fireEvent.click(btn('assemble-generate-chapter'));
    expect(mockGen.mutate).toHaveBeenCalled();
    expect(preview().value).toBe('CH PROSE');
  });

  it('Stitch is disabled until all scenes are done', () => {
    render(<ChapterAssembleView {...base} scenesAllDone={false} onAccept={vi.fn()} />);
    expect(btn('assemble-stitch').disabled).toBe(true);
  });

  it('Stitch (all done) calls the stitch endpoint and shows the degraded badge on fallback', () => {
    mockStitch.mutate.mockImplementation((_p, opts) => opts?.onSuccess?.(STITCH_RESULT));
    render(<ChapterAssembleView {...base} onAccept={vi.fn()} />);
    fireEvent.click(btn('assemble-stitch'));
    expect(mockStitch.mutate).toHaveBeenCalled();
    expect(screen.getByTestId('assemble-degraded')).toBeTruthy();
  });

  it('Accept WITHOUT edit inserts via onAccept and submits NO edit correction (H2)', () => {
    mockGen.mutate.mockImplementation((_p, opts) => opts?.onSuccess?.(CHAPTER_RESULT));
    const onAccept = vi.fn(() => true); // insert succeeded → correction-capture + clear proceed
    render(<ChapterAssembleView {...base} onAccept={onAccept} />);
    fireEvent.click(btn('assemble-generate-chapter'));
    fireEvent.click(btn('assemble-accept'));
    expect(onAccept).toHaveBeenCalledWith('CH PROSE');
    expect(mockCorrection.mutate).not.toHaveBeenCalled();
  });

  it('Accept AFTER an edit submits a kind=edit correction with the edited text', () => {
    mockGen.mutate.mockImplementation((_p, opts) => opts?.onSuccess?.(CHAPTER_RESULT));
    const onAccept = vi.fn(() => true); // insert succeeded → correction-capture + clear proceed
    render(<ChapterAssembleView {...base} onAccept={onAccept} />);
    fireEvent.click(btn('assemble-generate-chapter'));
    fireEvent.change(preview(), { target: { value: 'EDITED PROSE' } });
    fireEvent.click(btn('assemble-accept'));
    expect(mockCorrection.mutate).toHaveBeenCalledWith({ jobId: 'job-ch', body: { kind: 'edit', edited_text: 'EDITED PROSE' } });
    expect(onAccept).toHaveBeenCalledWith('EDITED PROSE');
  });

  it('Accept that FAILS to insert (no editor) keeps the preview — no clear, no edit correction (S1 GAP-2)', () => {
    mockGen.mutate.mockImplementation((_p, opts) => opts?.onSuccess?.(CHAPTER_RESULT));
    const onAccept = vi.fn(() => false); // e.g. no editor open on this chapter in the dock
    render(<ChapterAssembleView {...base} onAccept={onAccept} />);
    fireEvent.click(btn('assemble-generate-chapter'));
    fireEvent.change(preview(), { target: { value: 'EDITED PROSE' } });
    fireEvent.click(btn('assemble-accept'));
    expect(onAccept).toHaveBeenCalledWith('EDITED PROSE');
    expect(mockCorrection.mutate).not.toHaveBeenCalled();  // no correction captured on a failed accept
    expect(preview()).toBeTruthy();                        // the generated chapter is NOT lost
  });

  it('Regenerate submits a regenerate correction then re-runs the last action', () => {
    mockGen.mutate.mockImplementation((_p, opts) => opts?.onSuccess?.(CHAPTER_RESULT));
    render(<ChapterAssembleView {...base} onAccept={vi.fn()} />);
    fireEvent.click(btn('assemble-generate-chapter'));
    mockGen.mutate.mockClear();
    fireEvent.click(btn('assemble-regenerate'));
    expect(mockCorrection.mutate).toHaveBeenCalledWith({ jobId: 'job-ch', body: { kind: 'regenerate' } });
    expect(mockGen.mutate).toHaveBeenCalled(); // re-ran the chapter action
  });

  it('Reject submits a reject correction and clears the result', () => {
    mockGen.mutate.mockImplementation((_p, opts) => opts?.onSuccess?.(CHAPTER_RESULT));
    render(<ChapterAssembleView {...base} onAccept={vi.fn()} />);
    fireEvent.click(btn('assemble-generate-chapter'));
    fireEvent.click(btn('assemble-reject'));
    expect(mockCorrection.mutate).toHaveBeenCalledWith({ jobId: 'job-ch', body: { kind: 'reject' } });
    expect(screen.queryByTestId('assemble-preview')).toBeNull();
  });

  it('mode toggle patches work settings MERGED (preserves existing keys)', () => {
    render(<ChapterAssembleView {...base} settings={{ critic_model_ref: 'x' }} onAccept={vi.fn()} />);
    fireEvent.click(btn('assemble-mode-chapter'));
    expect(mockSetMode.mutate).toHaveBeenCalledWith({
      projectId: 'p', currentSettings: { critic_model_ref: 'x' }, mode: 'chapter',
    });
  });

  it('the active mode toggle button is disabled (no redundant patch)', () => {
    render(<ChapterAssembleView {...base} settings={{ assembly_mode: 'chapter' }} onAccept={vi.fn()} />);
    expect(btn('assemble-mode-chapter').disabled).toBe(true);
    expect(btn('assemble-mode-per_scene').disabled).toBe(false);
  });

  it('maps a NO_CHAPTER_PLAN error to its message key', () => {
    mockGen.error = { body: { detail: { code: 'NO_CHAPTER_PLAN' } } };
    render(<ChapterAssembleView {...base} onAccept={vi.fn()} />);
    // global i18n mock returns raw keys → assert the mapped key, not English text.
    expect(screen.getByTestId('assemble-error').textContent).toContain('errNoChapterPlan');
  });
});
