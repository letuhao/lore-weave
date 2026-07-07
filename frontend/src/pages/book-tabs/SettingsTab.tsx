import { useState, useEffect, useRef, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Save, Loader2, Upload, X, ChevronDown, Check, Plus, Info } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { booksApi, type Book } from '@/features/books/api';
import { glossaryApi } from '@/features/glossary/api';
import { tieringApi } from '@/features/glossary/tieringApi';
import { BookWorldSection } from '@/features/world/components/BookWorldSection';
import { LanguagePicker } from '@/components/shared';
import { cn } from '@/lib/utils';

type Props = {
  bookId: string;
  book: Book;
  onReload: () => void;
  /** review-impl fix (17_...docks.md, DOCK-2): injectable so BookSettingsPanel can reuse this
   *  component AS-IS instead of forking its ~400 lines of logic. Defaults to the classic route's
   *  own navigate() when omitted — same "caller injects, component never imports react-router or
   *  the studio host" shape as BookWorldSection's own onOpenWorld prop (dockable-gui.md DOCK-7). */
  onOpenWorld?: (worldId: string) => void;
};

export function SettingsTab({ bookId, book, onReload, onOpenWorld }: Props) {
  const { t } = useTranslation('books');
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const openWorld = onOpenWorld ?? ((worldId: string) => navigate(`/worlds/${worldId}`));

  // ── Form state ──
  const [title, setTitle] = useState(book.title);
  const [description, setDescription] = useState(book.description ?? '');
  const [language, setLanguage] = useState(book.original_language ?? '');
  const [summary, setSummary] = useState(book.summary ?? '');
  const [genreTags, setGenreTags] = useState<string[]>(book.genre_tags ?? []);
  const [saving, setSaving] = useState(false);
  // bug #23: visibility/sharing lives ONLY in the dedicated Sharing tab now (it also owns the
  // unlisted link + collaborators) — the duplicate control here was removed to de-clutter.

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
  }, [book]);

  // Fetch cover (revoke old blob URL to prevent memory leak)
  useEffect(() => {
    if (!accessToken || !book.has_cover) { setCoverUrl(null); return; }
    let revoked = false;
    booksApi.getCover(accessToken, bookId)
      .then((blob) => {
        if (revoked) return;
        setCoverUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return URL.createObjectURL(blob); });
      })
      .catch(() => setCoverUrl(null));
    return () => { revoked = true; };
  }, [accessToken, bookId, book.has_cover]);

  // Fetch genres for this book — the tiered ontology read (G4e retired the old flat
  // genre_groups /genres route; this book's genre CATALOG for the tag picker now
  // comes from GET .../ontology, same source useBookOntology/Manage use).
  const { data: genres = [] } = useQuery({
    queryKey: ['glossary-ontology', bookId],
    queryFn: () => tieringApi.getOntology(bookId, accessToken!).then((o) => o.genres),
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
    JSON.stringify(genreTags) !== JSON.stringify(book.genre_tags ?? []);

  // Genre impact preview
  const genreImpact = useMemo(() => {
    const result: { genre: string; attrs: string[] }[] = [];
    for (const g of genreTags) {
      const attrs: string[] = [];
      for (const k of kinds) {
        for (const a of k.default_attributes) {
          if ((a.genre_tags ?? []).includes(g)) attrs.push(a.name);
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

      toast.success(t('settings.saved'));
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
      toast.success(t('settings.cover_uploaded'));
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
      await booksApi.deleteCover(accessToken, bookId);
      setCoverUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return null; });
      toast.success(t('settings.cover_removed'));
      onReload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const toggleGenre = (name: string) => {
    setGenreTags((prev) =>
      prev.includes(name) ? prev.filter((g) => g !== name) : [...prev, name],
    );
  };

  const genreColor = (name: string) => genres.find((g) => g.name === name)?.color ?? '#8b5cf6';

  return (
    <div className="mx-auto max-w-2xl space-y-0 p-6">
      {/* ── Basic Info ── */}
      <SectionHeader>{t('settings.basic_info')}</SectionHeader>

      <div className="mb-5">
        <Label required>{t('settings.title')}</Label>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="w-full rounded-md border bg-background px-3 py-1.5 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
        />
      </div>

      <div className="mb-5">
        <Label>{t('settings.description')}</Label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={t('settings.description_placeholder')}
          rows={3}
          className="w-full rounded-md border bg-background px-3 py-1.5 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30 resize-vertical"
        />
      </div>

      <div className="mb-5 grid grid-cols-2 gap-4">
        <div>
          <Label>{t('settings.language')}</Label>
          <LanguagePicker
            value={language}
            onChange={setLanguage}
            placeholder={t('select_language')}
            className="w-full rounded-md border bg-background px-3 py-1.5 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
          />
        </div>
        <div>
          <Label>{t('settings.summary')} <span className="font-normal text-muted-foreground">{t('settings.summary_hint')}</span></Label>
          <input
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder={t('settings.summary_placeholder')}
            className="w-full rounded-md border bg-background px-3 py-1.5 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
          />
        </div>
      </div>

      <Divider />

      {/* ── Cover Image ── */}
      <SectionHeader>{t('settings.cover')}</SectionHeader>

      <div className="mb-5 flex gap-4 items-start">
        <div className="w-[100px] h-[150px] flex-shrink-0 rounded-md border bg-card flex items-center justify-center overflow-hidden">
          {coverUrl ? (
            <img src={coverUrl} alt={t('settings.cover')} className="h-full w-full object-cover" />
          ) : (
            <span className="text-[10px] text-muted-foreground">{t('settings.no_cover')}</span>
          )}
        </div>
        <div>
          <p className="mb-2 text-xs text-muted-foreground">{t('settings.cover_hint')}</p>
          <div className="flex gap-2">
            <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => { if (e.target.files?.[0]) void handleUploadCover(e.target.files[0]); }} />
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploadingCover}
              className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-secondary transition-colors disabled:opacity-50"
            >
              {uploadingCover ? <Loader2 className="h-3 w-3 animate-spin" /> : <Upload className="h-3 w-3" />}
              {t('settings.upload_cover')}
            </button>
            {coverUrl && (
              <button
                onClick={() => void handleRemoveCover()}
                className="rounded-md px-3 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/10 transition-colors"
              >
                {t('settings.remove')}
              </button>
            )}
          </div>
        </div>
      </div>

      <Divider />

      {/* ── Genre Tags ── */}
      <SectionHeader>{t('settings.genre_tags')}</SectionHeader>

      <div className="mb-2">
        <Label>{t('settings.genres')} <span className="font-normal text-muted-foreground">{t('settings.genres_hint')}</span></Label>

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
            {t('settings.add_genre')}
            <span className="flex-1" />
            <ChevronDown className={cn('h-3 w-3 transition-transform', genreDropdownOpen && 'rotate-180')} />
          </button>

          {genreDropdownOpen && (
            <>
              <div className="fixed inset-0 z-30" onClick={() => setGenreDropdownOpen(false)} />
              <div className="absolute left-0 right-0 z-40 mt-1 rounded-lg border bg-card shadow-lg overflow-hidden">
                {genres.length === 0 ? (
                  <p className="px-3 py-4 text-center text-xs text-muted-foreground">
                    {t('settings.no_genres')}
                    <br />{t('settings.create_genres')}
                  </p>
                ) : (
                  genres.map((g) => {
                    const isSelected = genreTags.includes(g.name);
                    return (
                      <button
                        key={g.genre_id}
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
                      </button>
                    );
                  })
                )}
              </div>
            </>
          )}
        </div>

        <p className="mt-1.5 text-[11px] text-muted-foreground">
          {t('settings.genres_help')}
        </p>
      </div>

      {/* Genre impact preview */}
      {genreTags.length > 0 && genreImpact.some((gi) => gi.attrs.length > 0) && (
        <div className="mb-5 rounded-md border border-violet-500/15 bg-violet-500/5 px-3 py-2.5">
          <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium text-violet-400">
            <Info className="h-3 w-3" />
            {t('settings.genre_impact')}
          </div>
          <div className="text-[11px] leading-relaxed text-muted-foreground">
            {genreImpact.map((gi) => (
              <div key={gi.genre}>
                <strong className="text-foreground">{gi.genre}</strong>
                {gi.attrs.length > 0
                  ? <> {t('settings.activates', { attrs: gi.attrs.join(', ') })}</>
                  : <> {t('settings.no_attrs')}</>}
              </div>
            ))}
          </div>
        </div>
      )}

      <Divider />

      {/* ── World (W6/G3 cross-link) ── */}
      <BookWorldSection
        bookId={bookId}
        worldId={book.world_id}
        onChanged={onReload}
        onOpenWorld={openWorld}
      />

      <Divider />

      {/* ── Save bar ── */}
      <div className="flex justify-end gap-2 border-t pt-4">
        <button
          onClick={() => {
            setTitle(book.title);
            setDescription(book.description ?? '');
            setLanguage(book.original_language ?? '');
            setSummary(book.summary ?? '');
            setGenreTags(book.genre_tags ?? []);
          }}
          disabled={!isDirty}
          className="rounded-md border px-4 py-1.5 text-xs font-medium text-foreground hover:bg-secondary disabled:opacity-30 transition-colors"
        >
          {t('settings.discard')}
        </button>
        <button
          onClick={() => void handleSave()}
          disabled={saving || !isDirty || !title.trim()}
          className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
          {t('settings.save')}
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
