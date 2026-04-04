import { useState, useEffect, useRef, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Save, Loader2, Upload, Trash2, X, ChevronDown, Check, Plus, Info } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { booksApi, type Book, type Visibility } from '@/features/books/api';
import { glossaryApi } from '@/features/glossary/api';
import type { GenreGroup, EntityKind } from '@/features/glossary/types';
import { cn } from '@/lib/utils';

type Props = {
  bookId: string;
  book: Book;
  onReload: () => void;
};

export function SettingsTab({ bookId, book, onReload }: Props) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  // ── Form state ──
  const [title, setTitle] = useState(book.title);
  const [description, setDescription] = useState(book.description ?? '');
  const [language, setLanguage] = useState(book.original_language ?? '');
  const [summary, setSummary] = useState(book.summary ?? '');
  const [genreTags, setGenreTags] = useState<string[]>(book.genre_tags ?? []);
  const [visibility, setVisibility] = useState<Visibility>((book.visibility as Visibility) ?? 'private');
  const [saving, setSaving] = useState(false);

  // ── Cover state ──
  const [coverUrl, setCoverUrl] = useState<string | null>(null);
  const [uploadingCover, setUploadingCover] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // ── Genre dropdown ──
  const [genreDropdownOpen, setGenreDropdownOpen] = useState(false);

  // Sync form when book changes externally
  useEffect(() => {
    setTitle(book.title);
    setDescription(book.description ?? '');
    setLanguage(book.original_language ?? '');
    setSummary(book.summary ?? '');
    setGenreTags(book.genre_tags ?? []);
    setVisibility((book.visibility as Visibility) ?? 'private');
  }, [book]);

  // Fetch cover
  useEffect(() => {
    if (!accessToken || !book.has_cover) { setCoverUrl(null); return; }
    booksApi.getCover(accessToken, bookId)
      .then((blob) => setCoverUrl(URL.createObjectURL(blob)))
      .catch(() => setCoverUrl(null));
  }, [accessToken, bookId, book.has_cover]);

  // Fetch genres for this book
  const { data: genres = [] } = useQuery({
    queryKey: ['glossary-genres', bookId],
    queryFn: () => glossaryApi.listGenres(bookId, accessToken!),
    enabled: !!accessToken,
  });

  // Fetch kinds for genre impact preview
  const { data: kinds = [] } = useQuery({
    queryKey: ['glossary-kinds'],
    queryFn: () => glossaryApi.getKinds(accessToken!),
    enabled: !!accessToken,
    staleTime: 10 * 60 * 1000,
  });

  // Dirty check
  const isDirty =
    title !== book.title ||
    description !== (book.description ?? '') ||
    language !== (book.original_language ?? '') ||
    summary !== (book.summary ?? '') ||
    JSON.stringify(genreTags) !== JSON.stringify(book.genre_tags ?? []) ||
    visibility !== ((book.visibility as Visibility) ?? 'private');

  // Genre impact preview
  const genreImpact = useMemo(() => {
    const result: { genre: string; attrs: string[] }[] = [];
    for (const g of genreTags) {
      const attrs: string[] = [];
      for (const k of kinds) {
        for (const a of k.default_attributes) {
          if (a.genre_tags.includes(g)) attrs.push(a.name);
        }
      }
      result.push({ genre: g, attrs });
    }
    return result;
  }, [genreTags, kinds]);

  const handleSave = async () => {
    if (!accessToken) return;
    setSaving(true);
    try {
      const changes: Record<string, unknown> = {};
      if (title !== book.title) changes.title = title;
      if (description !== (book.description ?? '')) changes.description = description || null;
      if (language !== (book.original_language ?? '')) changes.original_language = language || null;
      if (summary !== (book.summary ?? '')) changes.summary = summary || null;
      if (JSON.stringify(genreTags) !== JSON.stringify(book.genre_tags ?? [])) changes.genre_tags = genreTags;

      if (Object.keys(changes).length > 0) {
        await booksApi.patchBook(accessToken, bookId, changes);
      }

      // Visibility via sharing-service
      if (visibility !== ((book.visibility as Visibility) ?? 'private')) {
        await booksApi.patchSharing(accessToken, bookId, { visibility });
      }

      toast.success('Settings saved');
      onReload();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleUploadCover = async (file: File) => {
    if (!accessToken) return;
    setUploadingCover(true);
    try {
      await booksApi.uploadCover(accessToken, bookId, file);
      toast.success('Cover uploaded');
      onReload();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setUploadingCover(false);
    }
  };

  const handleRemoveCover = async () => {
    if (!accessToken) return;
    try {
      await fetch(`${import.meta.env.VITE_API_BASE || ''}/v1/books/${bookId}/cover`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      setCoverUrl(null);
      toast.success('Cover removed');
      onReload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const toggleGenre = (name: string) => {
    setGenreTags((prev) =>
      prev.includes(name) ? prev.filter((t) => t !== name) : [...prev, name],
    );
  };

  const genreColor = (name: string) => genres.find((g) => g.name === name)?.color ?? '#8b5cf6';

  return (
    <div className="mx-auto max-w-2xl space-y-0 p-6">
      {/* ── Basic Info ── */}
      <SectionHeader>Basic Information</SectionHeader>

      <div className="mb-5">
        <Label required>Title</Label>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="w-full rounded-md border bg-background px-3 py-1.5 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
        />
      </div>

      <div className="mb-5">
        <Label>Description</Label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="A brief summary of this book..."
          rows={3}
          className="w-full rounded-md border bg-background px-3 py-1.5 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30 resize-vertical"
        />
      </div>

      <div className="mb-5 grid grid-cols-2 gap-4">
        <div>
          <Label>Original Language</Label>
          <input
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            placeholder="e.g. ja, en, vi"
            className="w-full rounded-md border bg-background px-3 py-1.5 text-sm font-mono focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
          />
        </div>
        <div>
          <Label>Summary <span className="font-normal text-muted-foreground">(for catalog)</span></Label>
          <input
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="One-line summary shown in browse cards..."
            className="w-full rounded-md border bg-background px-3 py-1.5 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
          />
        </div>
      </div>

      <Divider />

      {/* ── Cover Image ── */}
      <SectionHeader>Cover Image</SectionHeader>

      <div className="mb-5 flex gap-4 items-start">
        <div className="w-[100px] h-[150px] flex-shrink-0 rounded-md border bg-card flex items-center justify-center overflow-hidden">
          {coverUrl ? (
            <img src={coverUrl} alt="Cover" className="h-full w-full object-cover" />
          ) : (
            <span className="text-[10px] text-muted-foreground">No cover</span>
          )}
        </div>
        <div>
          <p className="mb-2 text-xs text-muted-foreground">Upload a cover image (JPG/PNG, max 5 MB, recommended 2:3 ratio)</p>
          <div className="flex gap-2">
            <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => { if (e.target.files?.[0]) void handleUploadCover(e.target.files[0]); }} />
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploadingCover}
              className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-secondary transition-colors disabled:opacity-50"
            >
              {uploadingCover ? <Loader2 className="h-3 w-3 animate-spin" /> : <Upload className="h-3 w-3" />}
              Upload Cover
            </button>
            {coverUrl && (
              <button
                onClick={() => void handleRemoveCover()}
                className="rounded-md px-3 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/10 transition-colors"
              >
                Remove
              </button>
            )}
          </div>
        </div>
      </div>

      <Divider />

      {/* ── Genre Tags ── */}
      <SectionHeader>Genre Tags</SectionHeader>

      <div className="mb-2">
        <Label>Genres <span className="font-normal text-muted-foreground">Select genres that apply to this book</span></Label>

        {/* Selected pills */}
        {genreTags.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {genreTags.map((g) => (
              <span
                key={g}
                className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium"
                style={{ background: genreColor(g) + '20', color: genreColor(g) }}
              >
                <span className="h-1.5 w-1.5 rounded-sm" style={{ background: genreColor(g) }} />
                {g}
                <button
                  onClick={() => toggleGenre(g)}
                  className="ml-0.5 rounded-full p-px opacity-60 hover:opacity-100 transition-opacity"
                >
                  <X className="h-2.5 w-2.5" />
                </button>
              </span>
            ))}
          </div>
        )}

        {/* Dropdown */}
        <div className="relative">
          <button
            onClick={() => setGenreDropdownOpen(!genreDropdownOpen)}
            className="flex w-full items-center gap-2 rounded-md border bg-background px-3 py-1.5 text-xs text-muted-foreground hover:border-border/80 transition-colors"
          >
            <Plus className="h-3 w-3" />
            Add genre...
            <span className="flex-1" />
            <ChevronDown className={cn('h-3 w-3 transition-transform', genreDropdownOpen && 'rotate-180')} />
          </button>

          {genreDropdownOpen && (
            <>
              <div className="fixed inset-0 z-30" onClick={() => setGenreDropdownOpen(false)} />
              <div className="absolute left-0 right-0 z-40 mt-1 rounded-lg border bg-card shadow-lg overflow-hidden">
                {genres.length === 0 ? (
                  <p className="px-3 py-4 text-center text-xs text-muted-foreground">
                    No genres defined for this book yet.
                    <br />Create genres in Glossary &rarr; Genre Groups tab.
                  </p>
                ) : (
                  genres.map((g) => {
                    const isSelected = genreTags.includes(g.name);
                    return (
                      <button
                        key={g.id}
                        onClick={() => toggleGenre(g.name)}
                        className="flex w-full items-center gap-2.5 px-3 py-2 text-xs hover:bg-secondary/50 transition-colors"
                      >
                        <span className={cn(
                          'flex h-4 w-4 items-center justify-center rounded-sm border',
                          isSelected ? 'border-primary bg-primary' : 'border-border',
                        )}>
                          {isSelected && <Check className="h-2.5 w-2.5 text-primary-foreground" />}
                        </span>
                        <span className="h-2 w-2 rounded-sm" style={{ background: g.color }} />
                        <span className="flex-1 text-left">{g.name}</span>
                        {g.description && (
                          <span className="truncate text-[10px] text-muted-foreground max-w-[150px]">{g.description}</span>
                        )}
                      </button>
                    );
                  })
                )}
              </div>
            </>
          )}
        </div>

        <p className="mt-1.5 text-[11px] text-muted-foreground">
          Genres control which glossary attributes are active. Manage genres in Glossary &rarr; Genre Groups tab.
        </p>
      </div>

      {/* Genre impact preview */}
      {genreTags.length > 0 && genreImpact.some((gi) => gi.attrs.length > 0) && (
        <div className="mb-5 rounded-md border border-violet-500/15 bg-violet-500/5 px-3 py-2.5">
          <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium text-violet-400">
            <Info className="h-3 w-3" />
            Genre impact on glossary
          </div>
          <div className="text-[11px] leading-relaxed text-muted-foreground">
            {genreImpact.map((gi) => (
              <div key={gi.genre}>
                <strong className="text-foreground">{gi.genre}</strong>
                {gi.attrs.length > 0
                  ? <> activates: {gi.attrs.join(', ')}</>
                  : <> has no genre-specific attributes yet</>}
              </div>
            ))}
          </div>
        </div>
      )}

      <Divider />

      {/* ── Visibility ── */}
      <SectionHeader>Visibility</SectionHeader>

      <div className="mb-5 flex flex-col gap-2">
        {(['private', 'unlisted', 'public'] as const).map((v) => (
          <label
            key={v}
            className={cn(
              'flex cursor-pointer items-center gap-3 rounded-md border px-3 py-2.5 transition-colors',
              visibility === v ? 'border-primary bg-secondary' : 'hover:bg-secondary/50',
            )}
          >
            <input
              type="radio"
              name="visibility"
              value={v}
              checked={visibility === v}
              onChange={() => setVisibility(v)}
              className="accent-primary"
            />
            <div>
              <div className="text-xs font-medium capitalize">{v}</div>
              <div className="text-[10px] text-muted-foreground">
                {v === 'private' && 'Only you can see this book'}
                {v === 'unlisted' && 'Anyone with the link can read, but not listed in browse'}
                {v === 'public' && 'Visible to everyone in the catalog'}
              </div>
            </div>
          </label>
        ))}
      </div>

      {/* ── Save bar ── */}
      <div className="flex justify-end gap-2 border-t pt-4">
        <button
          onClick={() => {
            setTitle(book.title);
            setDescription(book.description ?? '');
            setLanguage(book.original_language ?? '');
            setSummary(book.summary ?? '');
            setGenreTags(book.genre_tags ?? []);
            setVisibility((book.visibility as Visibility) ?? 'private');
          }}
          disabled={!isDirty}
          className="rounded-md border px-4 py-1.5 text-xs font-medium text-foreground hover:bg-secondary disabled:opacity-30 transition-colors"
        >
          Discard Changes
        </button>
        <button
          onClick={() => void handleSave()}
          disabled={saving || !isDirty || !title.trim()}
          className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
          Save Settings
        </button>
      </div>
    </div>
  );
}

// ── Small helpers ─���

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-4 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
      {children}
    </div>
  );
}

function Label({ children, required }: { children: React.ReactNode; required?: boolean }) {
  return (
    <label className="mb-1.5 block text-xs font-medium">
      {children}
      {required && <span className="text-destructive"> *</span>}
    </label>
  );
}

function Divider() {
  return <div className="my-6 border-t" />;
}
