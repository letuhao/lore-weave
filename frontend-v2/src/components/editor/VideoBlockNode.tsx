import { Node, mergeAttributes } from '@tiptap/core';
import {
  ReactNodeViewRenderer,
  NodeViewWrapper,
  type NodeViewProps,
} from '@tiptap/react';
import { Video, Upload, Loader2, Lock, Play, Trash2, Replace, Accessibility, History } from 'lucide-react';
import { useState, useCallback, useRef, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { booksApi } from '@/features/books/api';
import { MediaPrompt } from './MediaPrompt';
import { getUploadContext } from './ImageBlockNode';

const MAX_VIDEO_SIZE = 100 * 1024 * 1024; // 100 MB
const ALLOWED_VIDEO_TYPES = new Set(['video/mp4', 'video/webm']);

/** Extract video duration client-side using HTMLVideoElement metadata */
function getVideoDuration(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const video = document.createElement('video');
    video.preload = 'metadata';
    video.onloadedmetadata = () => {
      const dur = isFinite(video.duration) ? Math.round(video.duration) : null;
      resolve(dur);
      URL.revokeObjectURL(video.src);
    };
    video.onerror = () => resolve(null);
    video.src = URL.createObjectURL(file);
  });
}

// History panel callback — shared with ImageBlockNode's _onOpenHistory
// Video reuses the same callback since VersionHistoryPanel works for any block type
let _onOpenVideoHistory: ((blockId: string, blockTitle: string, mediaSrc: string | null) => void) | null = null;
export function setOnOpenVideoHistory(fn: typeof _onOpenVideoHistory) {
  _onOpenVideoHistory = fn;
}

// --- Tiptap node extension ---
export const VideoBlockExtension = Node.create({
  name: 'videoBlock',
  group: 'block',
  atom: true,
  draggable: true,
  selectable: true,

  addAttributes() {
    return {
      blockId: {
        default: null,
        parseHTML: (el) => el.getAttribute('data-block-id'),
        renderHTML: (attrs) => ({ 'data-block-id': attrs.blockId }),
      },
      src: { default: null },
      alt: { default: '' },
      caption: { default: '' },
      ai_prompt: { default: '' },
      title: { default: '' },
      width: { default: 100 },
      duration: { default: null },
      size_bytes: { default: null },
      _mode: { default: 'ai', rendered: false },
    };
  },

  parseHTML() {
    return [{ tag: 'figure[data-video-block]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return ['figure', mergeAttributes(HTMLAttributes, { 'data-video-block': '' })];
  },

  addNodeView() {
    return ReactNodeViewRenderer(VideoBlockNodeView);
  },

  // Auto-generate blockId on first load for existing blocks without one
  onCreate() {
    const { editor } = this;
    const { doc, tr } = editor.state;
    let modified = false;
    doc.descendants((node, pos) => {
      if (node.type.name === 'videoBlock' && !node.attrs.blockId) {
        tr.setNodeMarkup(pos, undefined, {
          ...node.attrs,
          blockId: crypto.randomUUID().slice(0, 8),
        });
        modified = true;
      }
    });
    if (modified) editor.view.dispatch(tr);
  },
});

// --- Validation ---
function validateVideoFile(file: File): string | null {
  if (!ALLOWED_VIDEO_TYPES.has(file.type)) {
    return `Unsupported type: ${file.type}. Use MP4 or WebM.`;
  }
  if (file.size > MAX_VIDEO_SIZE) {
    return `File too large: ${(file.size / 1024 / 1024).toFixed(1)} MB. Max 100 MB.`;
  }
  return null;
}

// --- Format helpers ---
function formatDuration(seconds: number | null): string {
  if (!seconds) return '';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function formatSize(bytes: number | null): string {
  if (!bytes) return '';
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// --- Resize hook (same as ImageBlockNode) ---
function useResize(
  initialWidth: number,
  onResizeEnd: (width: number) => void,
  containerRef: React.RefObject<HTMLDivElement | null>,
) {
  const [currentWidth, setCurrentWidth] = useState(initialWidth);
  const isResizing = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(0);

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      e.stopPropagation();
      isResizing.current = true;
      startX.current = e.clientX;
      startWidth.current = currentWidth;

      const parentWidth = containerRef.current?.parentElement?.clientWidth ?? 1;

      const onMove = (ev: PointerEvent) => {
        if (!isResizing.current) return;
        const deltaX = ev.clientX - startX.current;
        const deltaPct = (deltaX / parentWidth) * 100;
        const newWidth = Math.round(Math.min(100, Math.max(10, startWidth.current + deltaPct)));
        setCurrentWidth(newWidth);
      };

      const onUp = () => {
        isResizing.current = false;
        document.removeEventListener('pointermove', onMove);
        document.removeEventListener('pointerup', onUp);
        setCurrentWidth((w) => {
          onResizeEnd(w);
          return w;
        });
      };

      document.addEventListener('pointermove', onMove);
      document.addEventListener('pointerup', onUp);
    },
    [currentWidth, onResizeEnd, containerRef],
  );

  return { currentWidth, setCurrentWidth, handlePointerDown };
}

// --- NodeView component ---
function VideoBlockNodeView({ node, updateAttributes, selected, editor, deleteNode }: NodeViewProps) {
  const editorMode = ((editor.storage as any).mediaGuard?.editorMode as string) || 'ai';
  const isClassic = editorMode === 'classic';
  const src = node.attrs.src as string | null;
  const alt = (node.attrs.alt as string) || '';
  const caption = (node.attrs.caption as string) || '';
  const width = (node.attrs.width as number) || 100;
  const duration = node.attrs.duration as number | null;
  const sizeBytes = node.attrs.size_bytes as number | null;
  const title = (node.attrs.title as string) || 'Video';
  const [showAlt, setShowAlt] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const handleResizeEnd = useCallback(
    (newWidth: number) => {
      updateAttributes({ width: newWidth });
    },
    [updateAttributes],
  );

  const { currentWidth, setCurrentWidth, handlePointerDown } = useResize(
    width,
    handleResizeEnd,
    containerRef,
  );

  useEffect(() => {
    setCurrentWidth(width);
  }, [width, setCurrentWidth]);

  // --- Upload logic ---
  const doUpload = useCallback(
    async (file: File) => {
      const err = validateVideoFile(file);
      if (err) {
        setUploadError(err);
        return;
      }
      const _uploadCtx = getUploadContext();
      if (!_uploadCtx) {
        setUploadError('Upload not available — save the chapter first.');
        return;
      }
      setUploading(true);
      setUploadPct(0);
      setUploadError(null);
      try {
        // Extract duration client-side
        const duration = await getVideoDuration(file);

        // Ensure blockId exists for versioned upload
        let blockId = node.attrs.blockId as string;
        if (!blockId) {
          blockId = crypto.randomUUID().slice(0, 8);
          updateAttributes({ blockId });
        }

        const result = await booksApi.uploadChapterMedia(
          _uploadCtx.token,
          _uploadCtx.bookId,
          _uploadCtx.chapterId,
          file,
          (pct) => setUploadPct(pct),
          blockId,
        );
        updateAttributes({
          src: result.url,
          title: result.filename,
          size_bytes: result.size,
          duration,
        });
      } catch (e: any) {
        setUploadError(e.message || 'Upload failed');
      } finally {
        setUploading(false);
      }
    },
    [updateAttributes, node.attrs.blockId],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) doUpload(file);
    },
    [doUpload],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => setDragOver(false), []);

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) doUpload(file);
      e.target.value = '';
    },
    [doUpload],
  );

  // --- Classic mode: compact locked placeholder ---
  if (isClassic) {
    return (
      <NodeViewWrapper className="group my-2">
        <div className="flex items-center gap-2 rounded-lg border bg-secondary px-3 py-2 text-muted-foreground">
          <Video className="h-4 w-4 flex-shrink-0 opacity-40" />
          <span className="flex-1 truncate text-xs">{title}</span>
          {sizeBytes && <span className="text-[9px] opacity-50">{formatSize(sizeBytes)}</span>}
          {duration && <span className="text-[9px] opacity-50">{formatDuration(duration)}</span>}
          {caption && (
            <span className="hidden text-[9px] opacity-50 group-hover:inline">{caption}</span>
          )}
          <span className="flex items-center gap-1 rounded bg-card px-1.5 py-0.5 text-[9px]">
            <Lock className="h-2.5 w-2.5" /> Switch to AI mode to edit
          </span>
        </div>
      </NodeViewWrapper>
    );
  }

  return (
    <NodeViewWrapper
      className={cn(
        'my-2 overflow-hidden rounded-lg border transition-shadow',
        selected ? 'ring-2 ring-primary/40' : 'hover:border-border-hover',
      )}
    >
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept="video/mp4,video/webm"
        className="hidden"
        onChange={handleFileSelect}
      />

      {/* Video container with percentage width */}
      <div
        ref={containerRef}
        className="group relative mx-auto"
        style={{ width: `${currentWidth}%` }}
      >
        {src ? (
          /* Player placeholder with hover overlay */
          <div className="relative flex aspect-video flex-col items-center justify-center bg-[#0a0a0a]">
            <div className="flex h-12 w-12 items-center justify-center rounded-full border-2 border-primary bg-primary/20 text-primary">
              <Play className="h-5 w-5" />
            </div>
            <span className="mt-2 text-xs text-muted-foreground">{title}</span>
            <span className="mt-0.5 text-[10px] text-muted-foreground/50">
              {[formatDuration(duration), formatSize(sizeBytes)].filter(Boolean).join(' · ')}
            </span>
            {/* Hover overlay with quick actions */}
            <div
              className="absolute inset-0 flex items-start justify-end gap-1 bg-black/0 p-2 opacity-0 transition-all group-hover:bg-black/30 group-hover:opacity-100"
              contentEditable={false}
            >
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                onMouseDown={(e) => e.preventDefault()}
                className="rounded bg-black/60 px-2 py-1 text-[10px] text-white backdrop-blur transition hover:bg-black/80"
                title="Replace video"
              >
                <Replace className="inline h-3 w-3" /> Replace
              </button>
              <button
                type="button"
                onClick={() => deleteNode()}
                onMouseDown={(e) => e.preventDefault()}
                className="rounded bg-black/60 px-2 py-1 text-[10px] text-white backdrop-blur transition hover:bg-destructive"
                title="Delete block"
              >
                <Trash2 className="inline h-3 w-3" />
              </button>
            </div>
          </div>
        ) : (
          /* Upload zone */
          <div
            className={cn(
              'flex flex-col items-center justify-center gap-2 border-2 border-dashed py-8 transition-colors',
              uploading
                ? 'border-primary/40 bg-primary/5'
                : dragOver
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border bg-secondary text-muted-foreground hover:border-primary/40 hover:text-foreground',
            )}
            contentEditable={false}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={() => !uploading && fileInputRef.current?.click()}
            style={{ cursor: uploading ? 'default' : 'pointer' }}
          >
            {uploading ? (
              <>
                <Loader2 className="h-6 w-6 animate-spin text-primary" />
                <span className="text-xs">Uploading... {uploadPct}%</span>
                <div className="mx-8 h-1.5 w-48 overflow-hidden rounded-full bg-secondary">
                  <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{ width: `${uploadPct}%` }}
                  />
                </div>
              </>
            ) : (
              <>
                <Upload className="h-6 w-6 opacity-40" />
                <span className="text-xs font-medium">
                  {dragOver ? 'Drop video here' : 'Drop a video or click to browse'}
                </span>
                <span className="text-[9px] opacity-50">MP4, WebM — Max 100 MB</span>
              </>
            )}
            {uploadError && (
              <span className="mt-1 text-[10px] text-destructive">{uploadError}</span>
            )}
          </div>
        )}

        {/* Resize handle — bottom-right corner (only when video loaded) */}
        {src && (
          <div
            className={cn(
              'absolute bottom-1 right-1 flex h-4 w-4 cursor-nwse-resize items-center justify-center rounded-sm bg-primary/70 transition-opacity',
              selected ? 'opacity-80' : 'opacity-0 group-hover:opacity-100',
            )}
            onPointerDown={handlePointerDown}
            contentEditable={false}
            title={`Width: ${currentWidth}%`}
          >
            <svg width="8" height="8" viewBox="0 0 8 8" fill="currentColor" className="text-primary-fg">
              <circle cx="6" cy="6" r="1" />
              <circle cx="6" cy="3" r="1" />
              <circle cx="3" cy="6" r="1" />
            </svg>
          </div>
        )}
      </div>

      {/* Caption bar with actions */}
      <div
        className="flex items-center gap-2 border-t bg-card px-3 py-1.5"
        contentEditable={false}
      >
        <Video className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
        <input
          type="text"
          value={caption}
          onChange={(e) => updateAttributes({ caption: e.target.value })}
          placeholder="Add a caption..."
          className="min-w-0 flex-1 bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground/40"
          aria-label="Video caption"
        />
        {currentWidth < 100 && (
          <span className="flex-shrink-0 font-mono text-[9px] text-muted-foreground">
            {currentWidth}%
          </span>
        )}
        {/* Replace video */}
        {src && (
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="flex flex-shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[9px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            title="Replace video"
          >
            <Replace className="h-3 w-3" />
          </button>
        )}
        {/* Version history */}
        {src && _onOpenVideoHistory && (
          <button
            type="button"
            onClick={() => _onOpenVideoHistory?.((node.attrs.blockId as string) || 'unknown', title, src)}
            className="flex flex-shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[9px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            title="Version history"
          >
            <History className="h-3 w-3" />
          </button>
        )}
        {/* Delete video block */}
        <button
          type="button"
          onClick={() => deleteNode()}
          className="flex flex-shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[9px] text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
          title="Delete video block"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </div>

      {/* Alt text — collapsible */}
      <div className="border-t" contentEditable={false}>
        <button
          type="button"
          onClick={() => setShowAlt(!showAlt)}
          className="flex w-full items-center gap-1.5 px-3 py-1 text-[10px] text-muted-foreground transition-colors hover:text-foreground"
          aria-expanded={showAlt}
        >
          <Accessibility className="h-3 w-3" />
          <span>Alt text</span>
          {alt && <span className="rounded bg-success/10 px-1 text-[8px] text-success">set</span>}
          <span className="ml-auto text-[9px]">{showAlt ? '▾' : '▸'}</span>
        </button>
        {showAlt && (
          <div className="border-t px-3 py-1.5">
            <input
              type="text"
              value={alt}
              onChange={(e) => updateAttributes({ alt: e.target.value })}
              placeholder="Describe this video for screen readers and EPUB export..."
              className="w-full bg-transparent text-[11px] text-foreground outline-none placeholder:text-muted-foreground/40"
              aria-label="Video alt text"
            />
            <p className="mt-1 text-[9px] text-muted-foreground/60">
              Used by screen readers, search, and EPUB export. Different from caption.
            </p>
          </div>
        )}
      </div>

      {/* AI Prompt — collapsible */}
      {/* AI Prompt — collapsible */}
      <MediaPrompt
        prompt={(node.attrs.ai_prompt as string) || ''}
        onChange={(val) => updateAttributes({ ai_prompt: val })}
        onRegenerate={() => {}}
        regenerateDisabled={true}
        regenerateLabel="Generate (coming soon)"
      />
      {/* Placeholder for future video generation errors */}
    </NodeViewWrapper>
  );
}
