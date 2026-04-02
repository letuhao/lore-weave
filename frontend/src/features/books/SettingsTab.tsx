import { useCallback, useEffect, useRef, useState } from 'react';
import { Camera, Save, Trash2, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { booksApi, type Book } from '@/features/books/api';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface SettingsTabProps {
  book: Book;
  onUpdate: () => void;
}

export function SettingsTab({ book, onUpdate }: SettingsTabProps) {
  const { accessToken } = useAuth();

  // ── Form state ────────────────────────────────────────────────────────────

  const [title, setTitle] = useState(book.title);
  const [description, setDescription] = useState(book.description ?? '');
  const [language, setLanguage] = useState(book.original_language ?? '');
  const [summary, setSummary] = useState(book.summary ?? '');
  const [isSaving, setIsSaving] = useState(false);

  // Reset form when book prop changes
  useEffect(() => {
    setTitle(book.title);
    setDescription(book.description ?? '');
    setLanguage(book.original_language ?? '');
    setSummary(book.summary ?? '');
  }, [book]);

  const dirty =
    title !== book.title ||
    description !== (book.description ?? '') ||
    language !== (book.original_language ?? '') ||
    summary !== (book.summary ?? '');

  // ── Cover state ───────────────────────────────────────────────────────────

  const [coverUrl, setCoverUrl] = useState<string | null>(null);
  const [coverLoading, setCoverLoading] = useState(false);
  const [coverUploading, setCoverUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadCover = useCallback(async () => {
    if (!accessToken || !book.has_cover) {
      setCoverUrl(null);
      return;
    }
    setCoverLoading(true);
    try {
      const blob = await booksApi.getCover(accessToken, book.book_id);
      setCoverUrl(URL.createObjectURL(blob));
    } catch {
      setCoverUrl(null);
    } finally {
      setCoverLoading(false);
    }
  }, [accessToken, book.book_id, book.has_cover]);

  useEffect(() => {
    void loadCover();
    return () => {
      if (coverUrl) URL.revokeObjectURL(coverUrl);
    };
  }, [loadCover]);

  // ── Save metadata ─────────────────────────────────────────────────────────

  async function handleSave() {
    if (!accessToken || !dirty) return;
    setIsSaving(true);
    try {
      await booksApi.patchBook(accessToken, book.book_id, {
        title: title.trim(),
        description: description.trim() || null,
        original_language: language.trim() || null,
        summary: summary.trim() || null,
      });
      toast.success('Book settings saved');
      onUpdate();
    } catch (e) {
      toast.error(`Failed to save: ${(e as Error).message}`);
    } finally {
      setIsSaving(false);
    }
  }

  // ── Cover upload ──────────────────────────────────────────────────────────

  async function handleCoverUpload(file: File) {
    if (!accessToken) return;
    if (!file.type.startsWith('image/')) {
      toast.error('Please select an image file');
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      toast.error('Cover image must be under 5 MB');
      return;
    }
    setCoverUploading(true);
    try {
      await booksApi.uploadCover(accessToken, book.book_id, file);
      toast.success('Cover uploaded');
      onUpdate();
      // Reload cover preview
      const blob = await booksApi.getCover(accessToken, book.book_id);
      if (coverUrl) URL.revokeObjectURL(coverUrl);
      setCoverUrl(URL.createObjectURL(blob));
    } catch (e) {
      toast.error(`Upload failed: ${(e as Error).message}`);
    } finally {
      setCoverUploading(false);
    }
  }

  async function handleCoverDelete() {
    if (!accessToken) return;
    try {
      await booksApi.deleteCover(accessToken, book.book_id);
      if (coverUrl) URL.revokeObjectURL(coverUrl);
      setCoverUrl(null);
      toast.success('Cover removed');
      onUpdate();
    } catch (e) {
      toast.error(`Failed to remove cover: ${(e as Error).message}`);
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="max-w-xl space-y-8">
      {/* ── Book Metadata ──────────────────────────────────────────────────── */}
      <section className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Book Details</h3>
          <p className="text-xs text-muted-foreground">
            Edit the basic information about your book.
          </p>
        </div>

        <div className="space-y-4 rounded-lg border border-border p-5">
          {/* Title */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">
              Title <span className="text-destructive">*</span>
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Book title"
              required
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

          {/* Description */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="A short description of your book..."
              rows={3}
              className="w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm leading-relaxed focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

          {/* Language */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">
              Original Language
            </label>
            <input
              type="text"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              placeholder="e.g. en, vi, zh-Hans"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            />
            <p className="text-[11px] text-muted-foreground">
              BCP-47 language code for the original text.
            </p>
          </div>

          {/* Summary */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Summary</label>
            <textarea
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder="Synopsis or summary visible to readers..."
              rows={4}
              className="w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm leading-relaxed focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

          {/* Save */}
          <div className="flex items-center gap-3 border-t border-border pt-4">
            <Button
              onClick={handleSave}
              disabled={!dirty || isSaving || !title.trim()}
              className="gap-1.5"
            >
              <Save className="h-3.5 w-3.5" />
              {isSaving ? 'Saving\u2026' : 'Save Changes'}
            </Button>
            {dirty && (
              <span className="text-xs text-muted-foreground">Unsaved changes</span>
            )}
          </div>
        </div>
      </section>

      {/* ── Cover Image ────────────────────────────────────────────────────── */}
      <section className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Cover Image</h3>
          <p className="text-xs text-muted-foreground">
            Upload a cover image for your book. Max 5 MB, any image format.
          </p>
        </div>

        <div className="rounded-lg border border-border p-5">
          <div className="flex items-start gap-6">
            {/* Cover preview */}
            <div
              className={cn(
                'flex h-40 w-28 shrink-0 items-center justify-center overflow-hidden rounded-md border border-border bg-muted/30',
                coverLoading && 'animate-pulse',
              )}
            >
              {coverUrl ? (
                <img
                  src={coverUrl}
                  alt="Book cover"
                  className="h-full w-full object-cover"
                />
              ) : (
                <Camera className="h-8 w-8 text-muted-foreground/30" />
              )}
            </div>

            {/* Actions */}
            <div className="flex flex-col gap-2">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void handleCoverUpload(file);
                  e.target.value = '';
                }}
              />
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5"
                disabled={coverUploading}
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload className="h-3.5 w-3.5" />
                {coverUploading
                  ? 'Uploading\u2026'
                  : coverUrl
                    ? 'Replace Cover'
                    : 'Upload Cover'}
              </Button>
              {coverUrl && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="gap-1.5 text-destructive hover:text-destructive"
                  onClick={handleCoverDelete}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Remove Cover
                </Button>
              )}
              <p className="mt-1 text-[11px] text-muted-foreground">
                Recommended: 2:3 ratio (e.g. 400 &times; 600 px)
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── Metadata (read-only) ───────────────────────────────────────────── */}
      <section className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Info</h3>
        </div>
        <div className="rounded-lg border border-border p-5">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-xs text-muted-foreground">Book ID</span>
              <p className="font-mono text-xs text-foreground/70">{book.book_id}</p>
            </div>
            <div>
              <span className="text-xs text-muted-foreground">Chapters</span>
              <p className="text-foreground">{book.chapter_count}</p>
            </div>
            <div>
              <span className="text-xs text-muted-foreground">State</span>
              <p className="text-foreground">{book.lifecycle_state}</p>
            </div>
            <div>
              <span className="text-xs text-muted-foreground">Created</span>
              <p className="text-foreground">
                {book.created_at ? new Date(book.created_at).toLocaleDateString() : '\u2014'}
              </p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
