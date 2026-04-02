import { Node, mergeAttributes } from '@tiptap/core';
import {
  ReactNodeViewRenderer,
  NodeViewWrapper,
  type NodeViewProps,
} from '@tiptap/react';
import { Video, Upload, Loader2, Lock, Play } from 'lucide-react';
import { useState, useCallback, useRef } from 'react';
import { cn } from '@/lib/utils';
import { booksApi } from '@/features/books/api';
import { MediaPrompt } from './MediaPrompt';
import { type ImageUploadContext, getUploadContext } from './ImageBlockNode';

const MAX_VIDEO_SIZE = 100 * 1024 * 1024; // 100 MB
const ALLOWED_VIDEO_TYPES = new Set(['video/mp4', 'video/webm']);

// --- Tiptap node extension ---
export const VideoBlockExtension = Node.create({
  name: 'videoBlock',
  group: 'block',
  atom: true,
  draggable: true,
  selectable: true,

  addAttributes() {
    return {
      src: { default: null },
      caption: { default: '' },
      ai_prompt: { default: '' },
      title: { default: '' },
      width: { default: 100 },
      duration: { default: null },
      size_bytes: { default: null },
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

// --- NodeView component ---
function VideoBlockNodeView({ node, updateAttributes, selected, editor }: NodeViewProps) {
  const editorMode = ((editor.storage as any).mediaGuard?.editorMode as string) || 'ai';
  const isClassic = editorMode === 'classic';
  const src = node.attrs.src as string | null;
  const caption = (node.attrs.caption as string) || '';
  const duration = node.attrs.duration as number | null;
  const sizeBytes = node.attrs.size_bytes as number | null;
  const title = (node.attrs.title as string) || 'Video';
  const [uploading, setUploading] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

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
        const result = await booksApi.uploadChapterMedia(
          _uploadCtx.token,
          _uploadCtx.bookId,
          _uploadCtx.chapterId,
          file,
          (pct) => setUploadPct(pct),
        );
        updateAttributes({
          src: result.url,
          title: result.filename,
          size_bytes: result.size,
        });
      } catch (e: any) {
        setUploadError(e.message || 'Upload failed');
      } finally {
        setUploading(false);
      }
    },
    [updateAttributes],
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
      <NodeViewWrapper className="my-2">
        <div className="flex items-center gap-2 rounded-lg border bg-secondary px-3 py-2 text-muted-foreground">
          <Video className="h-4 w-4 flex-shrink-0 opacity-40" />
          <span className="flex-1 truncate text-xs">{title}</span>
          {sizeBytes && <span className="text-[9px] opacity-50">{formatSize(sizeBytes)}</span>}
          <span className="flex items-center gap-1 rounded bg-card px-1.5 py-0.5 text-[9px]">
            <Lock className="h-2.5 w-2.5" /> AI mode
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

      {/* Video area */}
      {src ? (
        /* Player placeholder */
        <div className="relative flex aspect-video flex-col items-center justify-center bg-[#0a0a0a]">
          <div className="flex h-12 w-12 items-center justify-center rounded-full border-2 border-primary bg-primary/20 text-primary">
            <Play className="h-5 w-5" />
          </div>
          <span className="mt-2 text-xs text-muted-foreground">{title}</span>
          <span className="mt-0.5 text-[10px] text-muted-foreground/50">
            {[formatDuration(duration), formatSize(sizeBytes)].filter(Boolean).join(' · ')}
          </span>
        </div>
      ) : (
        /* Upload zone */
        <div
          className={cn(
            'flex aspect-video flex-col items-center justify-center gap-2 border-2 border-dashed transition-colors',
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

      {/* Caption bar */}
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
      </div>

      {/* AI Prompt */}
      <MediaPrompt
        prompt={(node.attrs.ai_prompt as string) || ''}
        onChange={(val) => updateAttributes({ ai_prompt: val })}
        onRegenerate={() => {}}
        regenerateDisabled={true}
        regenerateLabel="Generate (coming soon)"
      />
    </NodeViewWrapper>
  );
}
