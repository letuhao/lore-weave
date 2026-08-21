import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { BookOpen, Plus, ChevronRight, Languages, CircleHelp, Sparkles } from 'lucide-react';
import { FilterToolbar, Pagination, EmptyState, FormDialog, StatusBadge, SkeletonCard, LanguagePicker } from '@/components/shared';
import { LanguageDisplay } from '@/components/shared/LanguageDisplay';
import { PageHeader } from '@/components/layout/PageHeader';
import { useBooksList, hashToHue } from '@/features/books/hooks/useBooksList';
import { FB2ImportProgress } from '@/features/books/components/FB2ImportProgress';

export function BooksPage() {
  const { t } = useTranslation('books');
  const navigate = useNavigate();
  // C22 — the Translate intent routes here with ?intent=translate so the
  // workspace lands tailored to translation (a hint pointing to the per-book
  // translation surface), NOT a generic shell. Route-only: no new translator flow.
  const [searchParams] = useSearchParams();
  const translateIntent = searchParams.get('intent') === 'translate';
  const [helpOpen, setHelpOpen] = useState(false);
  const [tourStep, setTourStep] = useState<number | null>(null);

  // C1 — list/search/language-filter/create/coverage-batch logic extracted into
  // useBooksList() (docs/specs/2026-07-01-writing-studio/14_utility_panels.md Phase C1) so
  // this page and the studio `books` dock panel (BooksBrowserPanel) share one implementation.
  const {
    total,
    loading,
    error,
    search,
    setSearch,
    offset,
    setOffset,
    limit,
    createOpen,
    setCreateOpen,
    creating,
    newTitle,
    setNewTitle,
    newDesc,
    setNewDesc,
    newLang,
    setNewLang,
    newFB2File,
    setNewFB2File,
    newFB2ImportStage,
    newFB2ImportProgress,
    newFB2ImportJob,
    newFB2ImportError,
    langFilter,
    setLangFilter,
    bookLangs,
    filteredBooks,
    allLanguages,
    handleCreate,
    handleFB2Import,
    resetNewFB2Import,
  } = useBooksList();

  const isFB2ImportBusy = newFB2ImportStage === 'uploading' || newFB2ImportStage === 'processing';
  const handleCreateDialogChange = (open: boolean) => {
    if (!open && isFB2ImportBusy) return;
    setCreateOpen(open);
    if (!open) resetNewFB2Import();
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('workspace')}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <button onClick={() => { setTourStep(null); setHelpOpen(true); }} data-testid="books-open-guide" className="inline-flex items-center gap-2 rounded-md border px-3.5 py-2 text-sm font-medium transition-colors hover:bg-secondary">
              <CircleHelp className="h-4 w-4" />
              {t('help.open')}
            </button>
            <button onClick={() => { setTourStep(0); setHelpOpen(true); }} data-testid="books-start-tour" className="inline-flex items-center gap-2 rounded-md border px-3.5 py-2 text-sm font-medium transition-colors hover:bg-secondary">
              <Sparkles className="h-4 w-4" />
              {t('help.tour')}
            </button>
            <button onClick={() => setCreateOpen(true)} data-testid="book-create-button" className="btn-glow inline-flex items-center gap-2 rounded-md bg-primary px-3.5 py-2 text-sm font-medium text-primary-foreground transition-all hover:bg-primary/90">
              <Plus className="h-4 w-4" />
              {t('new_book')}
            </button>
          </div>
        }
      />

      <FormDialog
        open={helpOpen}
        onOpenChange={(open) => { setHelpOpen(open); if (!open) setTourStep(null); }}
        title={tourStep === null ? t('help.title') : t('help.steps.' + tourStep + '.title')}
        description={tourStep === null ? t('help.description') : t('help.steps.' + tourStep + '.description')}
        footer={tourStep === null ? (
          <button onClick={() => setTourStep(0)} className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90">
            {t('help.startTour')}
          </button>
        ) : (
          <>
            <button onClick={() => setTourStep((step) => (step !== null && step > 0 ? step - 1 : step))} disabled={tourStep === 0} className="rounded-md border px-4 py-2 text-sm font-medium transition-colors hover:bg-secondary disabled:opacity-50">
              {t('help.back')}
            </button>
            {tourStep < 2 ? (
              <button onClick={() => setTourStep((step) => (step !== null ? step + 1 : 0))} className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90">
                {t('help.next')}
              </button>
            ) : (
              <button onClick={() => { setHelpOpen(false); setTourStep(null); }} className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90">
                {t('help.done')}
              </button>
            )}
          </>
        )}
      >
        {tourStep === null ? (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">{t('help.intro')}</p>
            <ul className="list-disc space-y-2 pl-5 text-sm">
              {(t('help.items', { returnObjects: true }) as string[]).map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        ) : (
          <div className="rounded-md border bg-secondary/30 p-4 text-sm text-muted-foreground">
            {t('help.steps.' + tourStep + '.body')}
          </div>
        )}
      </FormDialog>

      {translateIntent && (
        <div
          data-testid="translate-intent-hint"
          className="flex items-start gap-2.5 rounded-md border border-primary/30 bg-primary/5 px-3.5 py-2.5 text-sm"
        >
          <Languages className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" />
          <span className="text-muted-foreground">
            {t('translateIntent.hint', {
              defaultValue:
                'Pick a book to translate — open it, then use the Translation tab to start a translation.',
            })}
          </span>
        </div>
      )}

      {error && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <FilterToolbar
        search={search}
        onSearchChange={setSearch}
        searchPlaceholder={t('search_placeholder')}
        trailing={
          <div className="flex items-center gap-3">
            {allLanguages.length > 1 && (
              <select
                value={langFilter}
                onChange={(e) => setLangFilter(e.target.value)}
                className="appearance-none rounded-md border bg-background px-3 py-2 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-ring/40"
              >
                <option value="">{t('all_languages')}</option>
                {allLanguages.map((l) => (
                  <option key={l} value={l}>{l}</option>
                ))}
              </select>
            )}
            <span className="text-xs text-muted-foreground">
              {t('book_count', { count: filteredBooks.length })}
            </span>
          </div>
        }
      />

      {/* Loading */}
      {loading && (
        <div className="space-y-2">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      )}

      {/* Empty state */}
      {!loading && filteredBooks.length === 0 && (
        <EmptyState
          icon={BookOpen}
          title={t('empty.title')}
          description={t('empty.description')}
          variant="primary"
          action={
            <button
              onClick={() => setCreateOpen(true)}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-3.5 py-2 text-sm font-medium text-primary-foreground"
            >
              <Plus className="h-4 w-4" />
              {t('new_book')}
            </button>
          }
        />
      )}

      {/* Book list */}
      {!loading && filteredBooks.length > 0 && (
        <div className="space-y-2">
          {filteredBooks.map((book) => (
            <Link
              key={book.book_id}
              to={`/books/${book.book_id}/studio`}
              data-testid="book-row"
              className="group flex items-center gap-4 rounded-lg border p-4 transition-all hover:border-[hsl(var(--border-hover,25_6%_24%))] hover:bg-card"
            >
              {/* Cover */}
              <div
                className="flex h-16 w-11 flex-shrink-0 items-end overflow-hidden rounded border border-[hsl(var(--border-hover,25_6%_24%))]"
                style={{
                  background: `linear-gradient(135deg, hsl(${hashToHue(book.book_id)} 30% 12%), hsl(${hashToHue(book.book_id)} 25% 16%))`,
                  boxShadow: 'inset 0 0 20px rgba(0,0,0,0.5)',
                }}
              >
                <span className="p-1 font-serif text-[6px] leading-tight" style={{ color: `hsl(${hashToHue(book.book_id)} 40% 75%)` }}>
                  {book.title.slice(0, 20)}
                </span>
              </div>

              {/* Info */}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate font-serif font-medium">{book.title}</span>
                  {book.visibility && <StatusBadge variant={book.visibility} />}
                </div>
                <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                  {book.original_language ? (
                    <LanguageDisplay code={book.original_language} />
                  ) : (
                    <span>{t('card.no_language')}</span>
                  )}
                  <span className="text-border">·</span>
                  <span>{t('card.chapters', { count: book.chapter_count })}</span>
                  {book.updated_at && (
                    <>
                      <span className="text-border">·</span>
                      <span>{new Date(book.updated_at).toLocaleDateString()}</span>
                    </>
                  )}
                </div>
                {book.genre_tags && book.genre_tags.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {book.genre_tags.slice(0, 4).map((g) => (
                      <span key={g} className="rounded-full border border-border bg-secondary px-1.5 py-px text-[9px] font-medium text-muted-foreground">
                        {g}
                      </span>
                    ))}
                    {book.genre_tags.length > 4 && (
                      <span className="rounded-full border border-border bg-secondary px-1.5 py-px text-[9px] font-medium text-muted-foreground">
                        +{book.genre_tags.length - 4}
                      </span>
                    )}
                  </div>
                )}
              </div>

              {/* Translation language dots */}
              {bookLangs[book.book_id] && bookLangs[book.book_id].length > 0 && (
                <div className="flex items-center gap-1" title={t('translated_to', { langs: bookLangs[book.book_id].join(', ') })}>
                  {bookLangs[book.book_id].map((lang) => (
                    <span
                      key={lang}
                      className="h-2 w-2 rounded-full bg-success"
                      title={lang}
                    />
                  ))}
                </div>
              )}

              <ChevronRight className="h-4 w-4 text-muted-foreground/30 transition-colors group-hover:text-muted-foreground" />
            </Link>
          ))}
        </div>
      )}

      <Pagination total={total} limit={limit} offset={offset} onChange={setOffset} />

      {/* Create book dialog */}
      <FormDialog
        open={createOpen}
        onOpenChange={handleCreateDialogChange}
        title={t('create.title')}
        description={t('create.description')}
        footer={
          <>
            <button
              onClick={() => handleCreateDialogChange(false)}
              data-testid="book-create-cancel"
              disabled={isFB2ImportBusy}
              className="rounded-md border px-4 py-2 text-sm font-medium transition-colors hover:bg-secondary"
            >
              {t('common.cancel', { ns: 'common' })}
            </button>
            <button
              onClick={() => {
                if (newFB2ImportStage === 'completed' && newFB2ImportJob) {
                  navigate(`/books/${newFB2ImportJob.book_id}/studio`);
                  return;
                }
                if (newFB2File) {
                  void handleFB2Import();
                  return;
                }
                // D-BOOKS-CREATE-TO-STUDIO: land straight in the Studio for a
                // manually created book, instead of back on the list waiting for a second click.
                void handleCreate().then((bookId) => {
                  if (bookId) navigate(`/books/${bookId}/studio`);
                });
              }}
              disabled={creating || isFB2ImportBusy || (!newFB2File && (!newTitle.trim() || !newLang))}
              data-testid="book-create-submit"
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
            >
              {newFB2ImportStage === 'completed' ? 'Open imported book' : t('create.submit')}
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('create.book_title')}</label>
            <input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder={t('create.book_title_placeholder')}
              data-testid="book-title-input"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('create.language')}</label>
            <LanguagePicker
              value={newLang}
              onChange={setNewLang}
              placeholder={t('select_language')}
              data-testid="book-language-input"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring/40"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('create.book_description')}</label>
            <textarea
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder={t('create.book_description_placeholder')}
              rows={3}
              data-testid="book-description-input"
              className="w-full resize-none rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Or import an FB2 book</label>
            <input
              type="file"
              accept=".fb2,application/x-fictionbook+xml,text/xml,application/xml"
              data-testid="book-fb2-import-input"
              onChange={(event) => setNewFB2File(event.target.files?.[0] ?? null)}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            />
            {newFB2File && <p className="text-xs text-muted-foreground">Source metadata will set the book title and details.</p>}
          </div>
          <FB2ImportProgress
            stage={newFB2ImportStage}
            progress={newFB2ImportProgress}
            job={newFB2ImportJob}
            error={newFB2ImportError}
          />
        </div>
      </FormDialog>
    </div>
  );
}
