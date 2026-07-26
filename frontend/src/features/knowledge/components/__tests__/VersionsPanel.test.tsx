// 14_kg_panels.md A3 — VersionsPanel migrated its two hand-rolled `fixed inset-0` modals
// (preview, rollback-confirm) onto FormDialog/ConfirmDialog (DOCK-9). This test locks in
// the resulting behaviour: opening/closing the preview, the diff toggle, and the rollback
// confirm flow, plus toast on success/conflict.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { toast } from 'sonner';
import type { Summary, SummaryVersion } from '../../types';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const rollbackMock = vi.fn();
const useGlobalSummaryVersionsMock = vi.fn();
vi.mock('../../hooks/useSummaryVersions', () => ({
  useGlobalSummaryVersions: (...args: unknown[]) => useGlobalSummaryVersionsMock(...args),
}));

vi.mock('../../api', () => ({
  isVersionConflict: (err: unknown) => (err as { conflict?: boolean } | undefined)?.conflict === true,
}));

import { VersionsPanel } from '../VersionsPanel';

function mkVersion(over: Partial<SummaryVersion> = {}): SummaryVersion {
  return {
    version_id: over.version_id ?? 'v1',
    version: over.version ?? 1,
    content: over.content ?? 'Old content',
    edit_source: over.edit_source ?? 'manual',
    created_at: over.created_at ?? '2026-01-01T00:00:00Z',
    ...over,
  } as SummaryVersion;
}

function mkSummary(over: Partial<Summary> = {}): Summary {
  return {
    content: over.content ?? 'Current content',
    version: over.version ?? 2,
    ...over,
  } as Summary;
}

function setVersions(items: SummaryVersion[], extra: Record<string, unknown> = {}) {
  useGlobalSummaryVersionsMock.mockReturnValue({
    items,
    isLoading: false,
    isError: false,
    error: null,
    rollback: rollbackMock,
    isRollingBack: false,
    ...extra,
  });
}

describe('VersionsPanel', () => {
  beforeEach(() => {
    rollbackMock.mockReset();
    useGlobalSummaryVersionsMock.mockReset();
  });

  it('renders no fixed inset-0 hand-rolled overlay markup (DOCK-9)', () => {
    setVersions([mkVersion()]);
    const { container } = render(
      <VersionsPanel currentSummary={mkSummary()} onClose={vi.fn()} />,
    );
    expect(container.innerHTML).not.toContain('fixed inset-0');
  });

  it('opens the preview dialog for a version and shows its content', async () => {
    setVersions([mkVersion({ version_id: 'v1', version: 3, content: 'Archived text' })]);
    render(<VersionsPanel currentSummary={mkSummary()} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTitle('global.versions.view'));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Archived text')).toBeInTheDocument();
  });

  it('toggles the diff view against the current summary', async () => {
    setVersions([mkVersion({ version_id: 'v1', content: 'Old content' })]);
    render(<VersionsPanel currentSummary={mkSummary({ content: 'New content' })} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTitle('global.versions.view'));
    const toggle = await screen.findByTestId('versions-diff-toggle');
    fireEvent.click(toggle);
    expect(await screen.findByTestId('versions-diff-view')).toBeInTheDocument();
  });

  it('rollback-from-preview opens the confirm dialog, and confirming calls rollback', async () => {
    setVersions([mkVersion({ version_id: 'v1', version: 3 })]);
    render(<VersionsPanel currentSummary={mkSummary({ version: 5 })} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTitle('global.versions.view'));
    fireEvent.click(await screen.findByText('global.versions.rollbackFromPreview'));

    const confirmButton = await screen.findByText('global.versions.confirm');
    rollbackMock.mockResolvedValue(undefined);
    fireEvent.click(confirmButton);

    await waitFor(() =>
      expect(rollbackMock).toHaveBeenCalledWith({ version: 3, expectedVersion: 5 }),
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it('rollback directly from the row also opens the confirm dialog', async () => {
    setVersions([mkVersion({ version_id: 'v1', version: 3 })]);
    render(<VersionsPanel currentSummary={mkSummary({ version: 5 })} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTitle('global.versions.rollback'));
    expect(await screen.findByText('global.versions.confirmTitle')).toBeInTheDocument();
  });

  it('shows a conflict toast when rollback rejects with a version conflict', async () => {
    setVersions([mkVersion({ version_id: 'v1', version: 3 })]);
    rollbackMock.mockRejectedValue({ conflict: true });
    render(<VersionsPanel currentSummary={mkSummary({ version: 5 })} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTitle('global.versions.rollback'));
    fireEvent.click(await screen.findByText('global.versions.confirm'));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('global.conflict'));
  });
});
