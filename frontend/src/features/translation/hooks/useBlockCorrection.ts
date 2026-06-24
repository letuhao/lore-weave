import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import type { JSONContent } from '@tiptap/react';
import { useAuth } from '@/auth';
import { versionsApi, type ChapterTranslation } from '../api';

/** Plain-text projection of a Tiptap block (mirrors BE _block_text). */
export function blockText(node: JSONContent | undefined): string {
  if (!node) return '';
  if (node.type === 'text') return node.text || '';
  if (node.type === 'hardBreak') return '\n';
  return (node.content || []).map(blockText).join('');
}

/**
 * T1 controller for per-block translation correction (model a). `saveBlock` patches
 * ONE block of the chapter's single human-version (get-or-created server-side, seeded
 * from the viewed `version`); the per-block LLM→human diff is captured as learning
 * gold server-side. Owns saving/dirty state (MVC); the panel only renders.
 *
 * Plain-text rebuild: the corrected block keeps its type/attrs but its inline content
 * collapses to a single text node (inline marks dropped — accepted for v1).
 */
export function useBlockCorrection(
  chapterId: string,
  version: ChapterTranslation | null,
  originalBlocks: JSONContent[],
  onBlockPatched: (index: number, block: JSONContent) => void,
) {
  const { accessToken } = useAuth();
  const { t } = useTranslation('translation');
  const [savingIndex, setSavingIndex] = useState<number | null>(null);
  const [dirty, setDirty] = useState<Set<number>>(() => new Set());

  const saveBlock = useCallback(
    async (index: number, newText: string, template: JSONContent) => {
      if (!accessToken || !version) return;
      if (newText === blockText(template)) return; // no-op edit — skip the round-trip
      const block: JSONContent = { ...template, content: [{ type: 'text', text: newText }] };
      setSavingIndex(index);
      try {
        await versionsApi.patchBlock(accessToken, chapterId, {
          target_language: version.target_language,
          base_version_id: version.id,
          block_index: index,
          block: block as Record<string, unknown>,
          source_block_text: blockText(originalBlocks[index]) || undefined,
        });
        onBlockPatched(index, block);
        setDirty((d) => {
          const n = new Set(d);
          n.add(index);
          return n;
        });
        toast.success(t('review.block_saved'));
      } catch (e) {
        toast.error(t('review.block_save_failed', { error: (e as Error).message }));
      } finally {
        setSavingIndex(null);
      }
    },
    [accessToken, version, chapterId, originalBlocks, onBlockPatched, t],
  );

  return { saveBlock, savingIndex, dirty };
}
