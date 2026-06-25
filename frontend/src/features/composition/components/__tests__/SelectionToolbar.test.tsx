import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from 'sonner';
import { SelectionToolbar } from '../SelectionToolbar';

// BubbleMenu portals via floating-ui — render its children inline so the toolbar
// content is testable. The stream + models are mocked; the editor is a fake.
vi.mock('@tiptap/react/menus', () => ({ BubbleMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));

const { streamState, start, stop, clearGhost } = vi.hoisted(() => ({
  streamState: { ghost: '', streaming: false, error: null as string | null },
  start: vi.fn(), stop: vi.fn(), clearGhost: vi.fn(),
}));
vi.mock('../../hooks/useCompositionStream', () => ({
  useCompositionStream: () => ({ ...streamState, start, stop, clearGhost }),
}));
// WS-C: the fake editor has no real PM `view`, so mock the tracked-range helper.
// `rangeNow` controls what the tracked handle reports as the live mapped range
// (null = the span was deleted/collapsed → the precise stale signal).
const { trackRangeMock, rangeRelease, rangeNow } = vi.hoisted(() => ({
  trackRangeMock: vi.fn(),
  rangeRelease: vi.fn(),
  rangeNow: { value: null as { from: number; to: number } | null },
}));
vi.mock('../../../../components/editor/TrackedPositions', () => ({
  trackRange: (...a: unknown[]) => {
    trackRangeMock(...a);
    return { current: () => rangeNow.value, release: rangeRelease };
  },
}));
vi.mock('../../../ai-models/api', () => ({
  aiModelsApi: {
    listUserModels: vi.fn().mockResolvedValue({
      items: [{ user_model_id: 'm1', is_active: true, alias: 'M1', provider_kind: 'openai', provider_model_name: 'gpt' }],
    }),
  },
}));

function fakeEditor(selText = 'the gate of ash', from = 5, to = 20, docSize = 100) {
  const chain: any = {};
  chain.focus = () => chain; chain.deleteRange = vi.fn(() => chain);
  chain.insertContentAt = vi.fn(() => chain); chain.run = vi.fn(() => true);
  return {
    _chain: chain,
    state: {
      selection: { from, to, empty: selText.length === 0 },
      doc: { content: { size: docSize }, textBetween: () => selText },
    },
    chain: () => chain,
  } as any;
}

function renderTB(editor: any) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SelectionToolbar editor={editor} projectId="p1" sceneContext="scene-9" token="t" />
    </QueryClientProvider>,
  );
}

describe('SelectionToolbar (T3.2)', () => {
  beforeEach(() => {
    start.mockReset(); stop.mockReset(); clearGhost.mockReset();
    trackRangeMock.mockReset(); rangeRelease.mockReset(); rangeNow.value = null;
    (toast.error as ReturnType<typeof vi.fn>).mockReset();
    streamState.ghost = ''; streamState.streaming = false; streamState.error = null;
  });

  it('running an op streams the selection-edit + tracks the range for Accept', async () => {
    const editor = fakeEditor();
    renderTB(editor);
    await waitFor(() => expect((screen.getByTestId('selection-model') as HTMLSelectElement).value).toBe('m1'));
    fireEvent.click(screen.getByTestId('selection-rewrite'));
    expect(start).toHaveBeenCalledTimes(1);
    expect(start.mock.calls[0][0]).toMatchObject({
      projectId: 'p1', selection: 'the gate of ash', operation: 'rewrite',
      sceneContext: 'scene-9', modelSource: 'user_model', modelRef: 'm1',
    });
    // WS-C: the captured selection is registered as a TRACKED range (not a raw {from,to}).
    expect(trackRangeMock).toHaveBeenCalledWith(editor, 5, 20);
  });

  it('Accept replaces the tracked range (remapped) with the ghost', async () => {
    const editor = fakeEditor('the gate of ash', 5, 20, 100);
    const { rerender } = renderTB(editor);
    await waitFor(() => expect((screen.getByTestId('selection-model') as HTMLSelectElement).value).toBe('m1'));
    fireEvent.click(screen.getByTestId('selection-expand'));
    // stream completes with a ghost; the tracked range reports its (remapped) span.
    streamState.ghost = 'EXPANDED PROSE';
    rangeNow.value = { from: 5, to: 20 };
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    rerender(
      <QueryClientProvider client={qc}>
        <SelectionToolbar editor={editor} projectId="p1" sceneContext="scene-9" token="t" />
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByTestId('selection-accept'));
    expect(editor._chain.deleteRange).toHaveBeenCalledWith({ from: 5, to: 20 });
    expect(editor._chain.insertContentAt).toHaveBeenCalledWith(5, 'EXPANDED PROSE');
  });

  it('Accept aborts (no replace) when the tracked range was deleted (.current() null)', async () => {
    const editor = fakeEditor('the gate of ash', 5, 20, 10);
    const { rerender } = renderTB(editor);
    await waitFor(() => expect((screen.getByTestId('selection-model') as HTMLSelectElement).value).toBe('m1'));
    fireEvent.click(screen.getByTestId('selection-rewrite'));
    streamState.ghost = 'NEW';
    rangeNow.value = null;   // the span was deleted/collapsed mid-stream
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    rerender(
      <QueryClientProvider client={qc}>
        <SelectionToolbar editor={editor} projectId="p1" sceneContext="scene-9" token="t" />
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByTestId('selection-accept'));
    expect(toast.error).toHaveBeenCalled();
    expect(editor._chain.deleteRange).not.toHaveBeenCalled();
  });

  it('Discard stops the stream and clears the ghost', async () => {
    renderTB(fakeEditor());
    await waitFor(() => expect((screen.getByTestId('selection-model') as HTMLSelectElement).value).toBe('m1'));
    fireEvent.click(screen.getByTestId('selection-describe'));
    fireEvent.click(screen.getByTestId('selection-discard'));
    expect(stop).toHaveBeenCalled();
    expect(clearGhost).toHaveBeenCalled();
  });

  it('disables the tools on an over-long selection', async () => {
    renderTB(fakeEditor('x'.repeat(9000)));
    expect(await screen.findByTestId('selection-too-long')).toBeInTheDocument();
    expect(screen.queryByTestId('selection-rewrite')).not.toBeInTheDocument();
  });
});
