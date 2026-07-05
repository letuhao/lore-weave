import { Node, mergeAttributes, type Editor } from '@tiptap/core';
import {
  ReactNodeViewRenderer,
  NodeViewWrapper,
  type NodeViewProps,
} from '@tiptap/react';
import { ImageIcon, Accessibility, Upload, Loader2, Lock, History, Trash2, Replace } from 'lucide-react';
import { useState, useCallback, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { booksApi } from '@/features/books/api';
import { MediaPrompt } from './MediaPrompt';
import { useResize } from './useResize';

// --- Upload context ------------------------------------------------------
// #16 Phase 2 (2.7) — PER-EDITOR-INSTANCE via `editor.storage.mediaUpload` (mirrors the
// `editor.storage.mediaGuard.editorMode` shape already used in TiptapEditor.tsx). Historically
// a module-level singleton (`_uploadCtx`/`setImageUploadContext`/`setOnOpenHistory`) — safe
// only because exactly one ChapterEditorPage was ever mounted at a time. Writing Studio's
// dockview allows MULTIPLE chapter tabs open simultaneously (each its own TiptapEditor
// instance); a singleton would silently misattribute uploads/history-opens to whichever tab
// last called the setter. The host now writes this via `TiptapEditorHandle.setUploadContext`
// (see TiptapEditor.tsx) straight onto the owning editor instance's own storage.
export interface ImageUploadContext {
  token: string;
  bookId: string;
  chapterId: string;
  /** Opens the media version-history panel for a block. Shared between image and video blocks
   *  — `VersionHistoryPanel` works for any block type. */
  onOpenHistory?: (blockId: string, blockTitle: string, mediaSrc: string | null) => void;
  /** Opens version history for a video block specifically. Kept as a distinct field only
   *  because legacy wired it from a second setter (`VideoBlockNode.setOnOpenVideoHistory`) —
   *  the two callbacks may point at the very same function. */
  onOpenVideoHistory?: (blockId: string, blockTitle: string, mediaSrc: string | null) => void;
}

/** Reads the CALLING editor instance's own upload context off `editor.storage.mediaUpload`.
 *  Accepts anything exposing `.storage` (a Tiptap `Editor`). For call sites that only have a
 *  ProseMirror `EditorView` (no NodeView `editor` prop in scope — see
 *  AudioAttachActionsExtension.ts), resolve the Editor via `(view.dom as any).editor` first
 *  (Tiptap attaches the owning Editor instance there) and pass that in. */
export function getUploadContext(editor: Pick<Editor, 'storage'> | null | undefined): ImageUploadContext | null {
  return ((editor?.storage as Record<string, unknown> | undefined)?.mediaUpload as ImageUploadContext | undefined) ?? null;
}

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
const ALLOWED_TYPES = new Set(['image/png', 'image/jpeg', 'image/gif', 'image/webp']);

// --- Tiptap node extension ---
export const ImageBlockExtension = Node.create({
  name: 'imageBlock',
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
      width: { default: 100 },
      title: { default: '' },
      ai_prompt: { default: '' },
      /** Explicit user_model_id chosen via the MediaPrompt model picker — never
       *  a silently-resolved default (D-MEDIA-MODEL-PICKER). */
      ai_model_id: { default: null },
      _mode: { default: 'ai', rendered: false }, // transient, forces NodeView re-render on mode switch
    };
  },

  parseHTML() {
    return [{ tag: 'figure[data-image-block]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return ['figure', mergeAttributes(HTMLAttributes, { 'data-image-block': '' })];
  },

  addNodeView() {
    return ReactNodeViewRenderer(ImageBlockNodeView);
  },

  // Auto-generate blockId on first insert (for version tracking)
  onCreate() {
    const { editor } = this;
    const { doc, tr } = editor.state;
    let modified = false;
    doc.descendants((node, pos) => {
      if (node.type.name === 'imageBlock' && !node.attrs.blockId) {
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

// --- Upload validation --- (returns an i18n key + params, or null when valid)
function validateFile(file: File): { key: string; params?: Record<string, unknown> } | null {
  if (!ALLOWED_TYPES.has(file.type)) {
    return { key: 'image.err_type', params: { type: file.type } };
  }
  if (file.size > MAX_FILE_SIZE) {
    return { key: 'image.err_size', params: { size: (file.size / 1024 / 1024).toFixed(1) } };
  }
  return null;
}

// --- NodeView component ---
function ImageBlockNodeView({ node, updateAttributes, selected, editor, deleteNode }: NodeViewProps) {
  const { t } = useTranslation('editor');
  const editorMode = ((editor.storage as any).mediaGuard?.editorMode as string) || 'ai';
  const isClassic = editorMode === 'classic';
  const uploadCtx = getUploadContext(editor);
  const src = node.attrs.src as string | null;
  const alt = (node.attrs.alt as string) || '';
  const caption = (node.attrs.caption as string) || '';
  const width = (node.attrs.width as number) || 100;
  const [showAlt, setShowAlt] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [regenerateError, setRegenerateError] = useState<string | null>(null);
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

  // Sync width when attrs change externally (e.g. undo/redo)
  useEffect(() => {
    setCurrentWidth(width);
  }, [width, setCurrentWidth]);

  const handleCaptionChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      updateAttributes({ caption: e.target.value });
    },
    [updateAttributes],
  );

  const handleAltChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      updateAttributes({ alt: e.target.value });
    },
    [updateAttributes],
  );

  // --- Upload logic ---
  const doUpload = useCallback(
    async (file: File) => {
      const err = validateFile(file);
      if (err) {
        setUploadError(t(err.key, err.params));
        return;
      }
      const ctx = getUploadContext(editor);
      if (!ctx) {
        setUploadError(t('image.upload_unavailable'));
        return;
      }
      setUploading(true);
      setUploadPct(0);
      setUploadError(null);
      try {
        // Ensure blockId exists for versioned upload
        let blockId = node.attrs.blockId as string;
        if (!blockId) {
          blockId = crypto.randomUUID().slice(0, 8);
          updateAttributes({ blockId });
        }

        const result = await booksApi.uploadChapterMedia(
          ctx.token,
          ctx.bookId,
          ctx.chapterId,
          file,
          (pct) => setUploadPct(pct),
          blockId,
        );
        updateAttributes({
          src: result.url,
          title: result.filename,
        });
      } catch (e: any) {
        setUploadError(e.message || t('image.upload_failed'));
      } finally {
        setUploading(false);
      }
    },
    [updateAttributes, node.attrs.blockId, editor],
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
      // Reset input so the same file can be re-selected
      e.target.value = '';
    },
    [doUpload],
  );

  const handlePaste = useCallback(
    (e: React.ClipboardEvent) => {
      const items = e.clipboardData.items;
      for (let i = 0; i < items.length; i++) {
        if (items[i].type.startsWith('image/')) {
          const file = items[i].getAsFile();
          if (file) {
            e.preventDefault();
            doUpload(file);
            return;
          }
        }
      }
    },
    [doUpload],
  );

  // --- AI Re-generate ---
  const handleRegenerate = useCallback(async () => {
    const prompt = (node.attrs.ai_prompt as string)?.trim();
    if (!prompt) return;
    const modelId = node.attrs.ai_model_id as string | null;
    if (!modelId) {
      setRegenerateError(t('image.regen_no_model'));
      return;
    }
    const ctx = getUploadContext(editor);
    if (!ctx) {
      setRegenerateError(t('image.regen_save_first'));
      return;
    }
    setRegenerating(true);
    setRegenerateError(null);
    try {
      const blockId = (node.attrs.blockId as string) || crypto.randomUUID().slice(0, 8);
      if (!node.attrs.blockId) updateAttributes({ blockId });
      const result = await booksApi.generateImage(ctx.token, ctx.bookId, ctx.chapterId, {
        block_id: blockId,
        prompt,
        model_source: 'user_model',
        model_ref: modelId,
      });
      updateAttributes({ src: result.url });
    } catch (e: any) {
      if (e.status === 402) {
        setRegenerateError(t('image.regen_no_provider'));
      } else {
        setRegenerateError(e.message || t('image.regen_failed'));
      }
    } finally {
      setRegenerating(false);
    }
  }, [node.attrs.ai_prompt, node.attrs.ai_model_id, node.attrs.blockId, updateAttributes, editor, t]);

  // --- Classic mode: compact locked placeholder with hover preview ---
  if (isClassic) {
    const title = (node.attrs.title as string) || t('image.default_title');
    return (
      <NodeViewWrapper className="group my-2">
        <div className="flex items-center gap-2 rounded-lg border bg-secondary px-3 py-2 text-muted-foreground">
          {/* Thumbnail preview on hover */}
          {src && (
            <img src={src} alt="" className="h-6 w-6 rounded object-cover opacity-50" draggable={false} />
          )}
          {!src && <ImageIcon className="h-4 w-4 flex-shrink-0 opacity-40" />}
          <span className="flex-1 truncate text-xs">{title}</span>
          {src && caption && (
            <span className="hidden text-[9px] opacity-50 group-hover:inline">
              {caption}
            </span>
          )}
          {src && uploadCtx?.onOpenHistory && (
            <button
              type="button"
              onClick={() => uploadCtx.onOpenHistory?.((node.attrs.blockId as string) || 'unknown', title, src)}
              className="flex flex-shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[9px] transition-colors hover:bg-card hover:text-foreground"
              title={t('image.version_history')}
            >
              <History className="h-2.5 w-2.5" />
            </button>
          )}
          <button
            type="button"
            onClick={() => {
              if (title && title !== t('image.default_title')) navigator.clipboard.writeText(title);
            }}
            className="hidden flex-shrink-0 rounded px-1.5 py-0.5 text-[9px] text-muted-foreground transition-colors hover:bg-card hover:text-foreground group-hover:flex"
            title={t('image.copy_filename')}
          >
            {t('image.copy')}
          </button>
          <span className="flex items-center gap-1 rounded bg-card px-1.5 py-0.5 text-[9px]">
            <Lock className="h-2.5 w-2.5" /> {t('image.ai_mode')}
          </span>
        </div>
        {/* Hover preview — shows larger thumbnail */}
        {src && (
          <div className="hidden overflow-hidden rounded-b-lg border border-t-0 group-hover:block">
            <img src={src} alt={alt} className="max-h-32 w-full object-cover opacity-70" draggable={false} />
          </div>
        )}
      </NodeViewWrapper>
    );
  }

  return (
    <NodeViewWrapper
      className={cn(
        'my-2 overflow-hidden rounded-lg border transition-shadow',
        selected ? 'ring-2 ring-primary/40' : 'hover:border-border-hover',
      )}
      onPaste={!src ? handlePaste : undefined}
    >
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/png,image/jpeg,image/gif,image/webp"
        className="hidden"
        onChange={handleFileSelect}
      />

      {/* Image container with percentage width */}
      <div
        ref={containerRef}
        className="group relative mx-auto"
        style={{ width: `${currentWidth}%` }}
      >
        {src ? (
          <div className="relative">
            <img
              src={src}
              alt={alt}
              title={node.attrs.title as string}
              className="block w-full rounded-t-lg object-cover"
              draggable={false}
            />
            {/* Hover overlay with quick actions */}
            <div
              className="absolute inset-0 flex items-start justify-end gap-1 rounded-t-lg bg-black/0 p-2 opacity-0 transition-all group-hover:bg-black/30 group-hover:opacity-100"
              contentEditable={false}
            >
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                onMouseDown={(e) => e.preventDefault()}
                className="rounded bg-black/60 px-2 py-1 text-[10px] text-white backdrop-blur transition hover:bg-black/80"
                title={t('image.replace_title')}
              >
                <Replace className="inline h-3 w-3" /> {t('image.replace')}
              </button>
              <button
                type="button"
                onClick={() => deleteNode()}
                onMouseDown={(e) => e.preventDefault()}
                className="rounded bg-black/60 px-2 py-1 text-[10px] text-white backdrop-blur transition hover:bg-destructive"
                title={t('image.delete_block')}
              >
                <Trash2 className="inline h-3 w-3" />
              </button>
            </div>
          </div>
        ) : (
          /* Upload zone */
          <div
            className={cn(
              'flex flex-col items-center justify-center gap-2 rounded-t-lg border-2 border-dashed py-8 transition-colors',
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
                <span className="text-xs">{t('image.uploading', { pct: uploadPct })}</span>
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
                  {dragOver ? t('image.drop_here') : t('image.drop_hint')}
                </span>
                <span className="text-[9px] opacity-50">
                  {t('image.formats')}
                </span>
              </>
            )}
            {uploadError && (
              <span className="mt-1 text-[10px] text-destructive">{uploadError}</span>
            )}
          </div>
        )}

        {/* Resize handle — bottom-right corner (only when image loaded) */}
        {src && (
          <div
            className={cn(
              'absolute bottom-1 right-1 flex h-4 w-4 cursor-nwse-resize items-center justify-center rounded-sm bg-primary/70 transition-opacity',
              selected ? 'opacity-80' : 'opacity-0 group-hover:opacity-100',
            )}
            onPointerDown={handlePointerDown}
            contentEditable={false}
            title={t('image.width_title', { width: currentWidth })}
          >
            <svg width="8" height="8" viewBox="0 0 8 8" fill="currentColor" className="text-primary-fg">
              <circle cx="6" cy="6" r="1" />
              <circle cx="6" cy="3" r="1" />
              <circle cx="3" cy="6" r="1" />
            </svg>
          </div>
        )}
      </div>

      {/* Caption + metadata bar */}
      <div
        className="flex items-center gap-2 border-t bg-card px-3 py-1.5"
        contentEditable={false}
      >
        <ImageIcon className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
        <input
          type="text"
          value={caption}
          onChange={handleCaptionChange}
          placeholder={t('image.caption_placeholder')}
          className="min-w-0 flex-1 bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground/40"
          aria-label={t('image.caption_aria')}
        />
        {currentWidth < 100 && (
          <span className="flex-shrink-0 font-mono text-[9px] text-muted-foreground">
            {currentWidth}%
          </span>
        )}
        {/* Replace image — re-open file picker */}
        {src && (
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="flex flex-shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[9px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            title={t('image.replace_title')}
          >
            <Replace className="h-3 w-3" />
          </button>
        )}
        {src && uploadCtx?.onOpenHistory && (
          <button
            type="button"
            onClick={() => uploadCtx.onOpenHistory?.((node.attrs.blockId as string) || 'unknown', (node.attrs.title as string) || t('image.default_title'), src)}
            className="flex flex-shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[9px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            title={t('image.version_history')}
          >
            <History className="h-3 w-3" />
          </button>
        )}
        {/* Delete image block */}
        <button
          type="button"
          onClick={() => deleteNode()}
          className="flex flex-shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[9px] text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
          title={t('image.delete_image_block')}
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
          <span>{t('image.alt_text')}</span>
          {alt && <span className="rounded bg-success/10 px-1 text-[8px] text-success">{t('image.alt_set')}</span>}
          <span className="ml-auto text-[9px]">{showAlt ? '▾' : '▸'}</span>
        </button>
        {showAlt && (
          <div className="border-t px-3 py-1.5">
            <input
              type="text"
              value={alt}
              onChange={handleAltChange}
              placeholder={t('image.alt_placeholder')}
              className="w-full bg-transparent text-[11px] text-foreground outline-none placeholder:text-muted-foreground/40"
              aria-label={t('image.alt_aria')}
            />
            <p className="mt-1 text-[9px] text-muted-foreground/60">
              {t('image.alt_note')}
            </p>
          </div>
        )}
      </div>

      {/* AI Prompt — collapsible */}
      <MediaPrompt
        prompt={(node.attrs.ai_prompt as string) || ''}
        onChange={(val) => updateAttributes({ ai_prompt: val })}
        onRegenerate={() => handleRegenerate()}
        regenerateDisabled={
          regenerating || !(node.attrs.ai_prompt as string)?.trim() || !(node.attrs.ai_model_id as string | null)
        }
        regenerateLabel={regenerating ? t('media.generating') : t('media.regenerate')}
        modelCapability="image_gen"
        modelId={(node.attrs.ai_model_id as string | null) ?? null}
        onModelChange={(id) => updateAttributes({ ai_model_id: id })}
      />
      {regenerateError && (
        <div className="border-t px-3 py-1 text-[10px] text-destructive" contentEditable={false}>
          {regenerateError}
        </div>
      )}
    </NodeViewWrapper>
  );
}
