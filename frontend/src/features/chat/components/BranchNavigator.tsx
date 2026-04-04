import { useCallback, useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight, GitBranch } from 'lucide-react';
import { useAuth } from '@/auth';
import { chatApi } from '../api';
import type { BranchInfo } from '../types';

interface BranchNavigatorProps {
  sessionId: string;
  /** The sequence number where the fork happened (the edited message's seq) */
  forkSequenceNum: number;
  /** Called when user navigates to a different branch */
  onSwitchBranch: (branchId: number) => void;
  /** Currently active branch_id */
  activeBranchId: number;
}

export function BranchNavigator({
  sessionId,
  forkSequenceNum,
  onSwitchBranch,
  activeBranchId,
}: BranchNavigatorProps) {
  const { accessToken } = useAuth();
  const [branches, setBranches] = useState<BranchInfo[]>([]);
  const [loading, setLoading] = useState(false);

  const loadBranches = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const res = await chatApi.listBranches(accessToken, sessionId, forkSequenceNum);
      setBranches(res.branches);
    } catch {
      setBranches([]);
    } finally {
      setLoading(false);
    }
  }, [accessToken, sessionId, forkSequenceNum]);

  useEffect(() => {
    void loadBranches();
  }, [loadBranches]);

  if (loading || branches.length <= 1) return null;

  let currentIndex = branches.findIndex((b) => b.branch_id === activeBranchId);
  if (currentIndex === -1) currentIndex = 0; // Fallback to first branch
  const total = branches.length;
  const displayIndex = currentIndex + 1;

  function goPrev() {
    if (currentIndex > 0) {
      onSwitchBranch(branches[currentIndex - 1].branch_id);
    }
  }

  function goNext() {
    if (currentIndex < total - 1) {
      onSwitchBranch(branches[currentIndex + 1].branch_id);
    }
  }

  return (
    <div className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
      <GitBranch className="h-3 w-3" />
      <button
        type="button"
        onClick={goPrev}
        disabled={currentIndex <= 0}
        className="rounded p-0.5 hover:bg-secondary hover:text-foreground disabled:opacity-30 disabled:cursor-default transition-colors"
      >
        <ChevronLeft className="h-3 w-3" />
      </button>
      <span className="font-mono text-[10px]">
        {displayIndex} / {total}
      </span>
      <button
        type="button"
        onClick={goNext}
        disabled={currentIndex >= total - 1}
        className="rounded p-0.5 hover:bg-secondary hover:text-foreground disabled:opacity-30 disabled:cursor-default transition-colors"
      >
        <ChevronRight className="h-3 w-3" />
      </button>
    </div>
  );
}
