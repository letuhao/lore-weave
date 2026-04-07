import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Eye, EyeOff } from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { versionsApi, type ChapterTranslation } from '@/features/translation/api';
import { BlockAlignedReview, computeReviewStats } from '@/features/translation/components/BlockAlignedReview';
import { SplitCompareView } from '@/features/translation/components/SplitCompareView';
import { cn } from '@/lib/utils';
import type { JSONContent } from '@tiptap/react';

export default function TranslationReviewPage() {
  const { bookId, chapterId, versionId } = useParams<{ bookId: string; chapterId: string; versionId: string }>();
  const { accessToken } = useAuth();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [originalBlocks, setOriginalBlocks] = useState<JSONContent[]>([]);
  const [translatedBlocks, setTranslatedBlocks] = useState<JSONContent[]>([]);
  const [version, setVersion] = useState<ChapterTranslation | null>(null);
  const [bookTitle, setBookTitle] = useState('');
  const [chapterTitle, setChapterTitle] = useState('');
  const [isBlockMode, setIsBlockMode] = useState(false);
  const [showPassthrough, setShowPassthrough] = useState(true);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  // Version list for switcher
  const [versions, setVersions] = useState<{ id: string; version_num: number; target_language: string; status: string }[]>([]);

  useEffect(() => {
    if (!accessToken || !bookId || !chapterId || !versionId) return;
    let mounted = true;
    setLoading(true);

    Promise.all([
      // Load original chapter
      booksApi.getDraft(accessToken, bookId, chapterId).catch(() => null),
      // Load translation version
      versionsApi.getChapterVersion(accessToken, chapterId, versionId).catch(() => null),
      // Load book info
      booksApi.getBook(accessToken, bookId).catch(() => null),
      // Load version list
      versionsApi.listChapterVersions(accessToken, chapterId).catch(() => null),
    ]).then(([draft, ver, book, verList]) => {
      if (!mounted) return;

      // Original blocks from Tiptap JSON body
      if (draft?.body && typeof draft.body === 'object' && Array.isArray((draft.body as any).content)) {
        setOriginalBlocks((draft.body as any).content);
      }

      if (ver) {
        setVersion(ver);
        // Block mode: JSONB translation
        if (ver.translated_body_format === 'json' && Array.isArray(ver.translated_body_json)) {
          setTranslatedBlocks(ver.translated_body_json as JSONContent[]);
          setIsBlockMode(true);
        } else {
          setIsBlockMode(false);
        }
      }

      if (book) {
        setBookTitle(book.title || '');
      }

      // Chapter title from draft
      if (draft) {
        setChapterTitle((draft as any).title || '');
      }

      // Version list
      if (verList) {
        const lang = ver?.target_language;
        const langVersions = (verList as any).languages?.find((l: any) => l.target_language === lang);
        if (langVersions?.versions) {
          setVersions(langVersions.versions.map((v: any) => ({
            id: v.id,
            version_num: v.version_num,
            target_language: v.target_language,
            status: v.status,
          })));
        }
      }
    }).finally(() => {
      if (mounted) setLoading(false);
    });

    return () => { mounted = false; };
  }, [accessToken, bookId, chapterId, versionId]);

  const handleVersionSwitch = useCallback((newVersionId: string) => {
    navigate(`/books/${bookId}/chapters/${chapterId}/review/${newVersionId}`, { replace: true });
  }, [navigate, bookId, chapterId]);

  // Keyboard navigation
  useEffect(() => {
    if (!isBlockMode) return;
    const maxIdx = Math.max(originalBlocks.length, translatedBlocks.length) - 1;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex(prev => Math.min((prev ?? -1) + 1, maxIdx));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex(prev => Math.max((prev ?? 1) - 1, 0));
      } else if (e.key === 'Escape') {
        setActiveIndex(null);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isBlockMode, originalBlocks.length, translatedBlocks.length]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  const stats = isBlockMode ? computeReviewStats(originalBlocks, translatedBlocks) : null;

  return (
    <div className="flex h-screen flex-col bg-background">
      {/* ── Toolbar ─────────────────────────────────────────────────── */}
      <div className="h-11 shrink-0 border-b border-border flex items-center justify-between px-4 bg-card">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back
          </button>
          <div className="h-4 w-px bg-border" />
          <div className="text-xs">
            <span className="text-muted-foreground">{bookTitle}</span>
            {chapterTitle && <span className="text-muted-foreground"> / {chapterTitle}</span>}
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Language pair */}
          {version && (
            <span className="text-[11px] font-medium">
              <span className="text-primary">{version.source_language ?? 'Source'}</span>
              <span className="text-muted-foreground mx-1.5">&rarr;</span>
              <span className="text-[#3da692]">{version.target_language}</span>
            </span>
          )}

          {/* Version selector */}
          {versions.length > 1 && (
            <select
              value={versionId}
              onChange={e => handleVersionSwitch(e.target.value)}
              className="rounded border bg-input px-2 py-0.5 text-[11px] focus:border-ring focus:outline-none"
            >
              {versions.map(v => (
                <option key={v.id} value={v.id}>
                  v{v.version_num} ({v.status})
                </option>
              ))}
            </select>
          )}

          {/* Stats */}
          {stats && (
            <span className="text-[10px] text-muted-foreground font-mono">
              {stats.translated}/{stats.translate + stats.caption} blocks
              {stats.empty > 0 && <span className="text-[#e8a832] ml-1">({stats.empty} empty)</span>}
            </span>
          )}

          {/* Toggle passthrough */}
          {isBlockMode && (
            <button
              onClick={() => setShowPassthrough(p => !p)}
              className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
              title={showPassthrough ? 'Hide unchanged blocks' : 'Show all blocks'}
            >
              {showPassthrough ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
              {showPassthrough ? 'All' : 'Translatable'}
            </button>
          )}

          {/* Mode badge */}
          <span className={cn(
            'rounded-full px-2 py-0.5 text-[9px] font-semibold',
            isBlockMode ? 'bg-[#8b5cf6]/10 text-[#8b5cf6]' : 'bg-secondary text-muted-foreground',
          )}>
            {isBlockMode ? 'Block' : 'Text'}
          </span>
        </div>
      </div>

      {/* ── Pane headers ────────────────────────────────────────────── */}
      {isBlockMode && (
        <div className="flex shrink-0 border-b border-border">
          <div className="w-9 shrink-0 border-r border-border/30" />
          <div className="flex-1 px-4 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-primary/70">
            Original
          </div>
          <div className="w-px bg-border/50" />
          <div className="flex-1 px-4 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-[#3da692]/70">
            Translation
          </div>
        </div>
      )}

      {/* ── Content ─────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
        {isBlockMode ? (
          <BlockAlignedReview
            originalBlocks={originalBlocks}
            translatedBlocks={translatedBlocks}
            showPassthrough={showPassthrough}
            activeIndex={activeIndex}
            onBlockClick={setActiveIndex}
          />
        ) : (
          <SplitCompareView
            bookId={bookId!}
            chapterId={chapterId!}
            versionId={versionId!}
            originalLanguage={version?.source_language ?? undefined}
            targetLanguage={version?.target_language ?? ''}
          />
        )}
      </div>
    </div>
  );
}
