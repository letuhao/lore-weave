import { useState, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { BookOpen, User, Languages, TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils';
import { PageHeader } from '@/components/layout/PageHeader';
import { Skeleton } from '@/components/shared';
import {
  leaderboardApi,
  type LeaderboardBook,
  type LeaderboardAuthor,
  type LeaderboardTranslator,
} from '@/features/leaderboard/api';
import { PeriodSelector } from '@/features/leaderboard/PeriodSelector';
import { FilterChips } from '@/features/leaderboard/FilterChips';
import { Podium } from '@/features/leaderboard/Podium';
import { RankingList } from '@/features/leaderboard/RankingList';
import { AuthorList } from '@/features/leaderboard/AuthorList';
import { TranslatorList } from '@/features/leaderboard/TranslatorList';
import { QuickStatsCards } from '@/features/leaderboard/QuickStatsCards';

type Tab = 'books' | 'authors' | 'translators' | 'trending';

const PAGE_SIZE = 20;

const tabs: { key: Tab; icon: React.ElementType; labelKey: string }[] = [
  { key: 'books', icon: BookOpen, labelKey: 'tabs.books' },
  { key: 'authors', icon: User, labelKey: 'tabs.authors' },
  { key: 'translators', icon: Languages, labelKey: 'tabs.translators' },
  { key: 'trending', icon: TrendingUp, labelKey: 'tabs.trending' },
];

export function LeaderboardPage() {
  const { t } = useTranslation('leaderboard');
  const [activeTab, setActiveTab] = useState<Tab>('books');
  const [period, setPeriod] = useState('30d');
  const [genre, setGenre] = useState('');
  const [language, setLanguage] = useState('');
  const [sort, setSort] = useState('');

  // Books state
  const [books, setBooks] = useState<LeaderboardBook[]>([]);
  const [booksTotal, setBooksTotal] = useState(0);
  const [booksLoading, setBooksLoading] = useState(false);

  // Authors state
  const [authors, setAuthors] = useState<LeaderboardAuthor[]>([]);
  const [authorsTotal, setAuthorsTotal] = useState(0);
  const [authorsLoading, setAuthorsLoading] = useState(false);

  // Translators state
  const [translators, setTranslators] = useState<LeaderboardTranslator[]>([]);
  const [translatorsTotal, setTranslatorsTotal] = useState(0);
  const [translatorsLoading, setTranslatorsLoading] = useState(false);

  // Quick-stats previews (separate from full lists to avoid overwriting)
  const [previewAuthors, setPreviewAuthors] = useState<LeaderboardAuthor[]>([]);
  const [previewTranslators, setPreviewTranslators] = useState<LeaderboardTranslator[]>([]);

  // ── Fetch functions ─────────────────────────────────────────────────────

  const fetchBooks = useCallback(
    async (offset = 0, append = false) => {
      setBooksLoading(true);
      try {
        const sortParam = activeTab === 'trending' ? 'trending' : sort || undefined;
        const data = await leaderboardApi.listBooks({
          period,
          genre: genre || undefined,
          language: language || undefined,
          sort: sortParam,
          limit: PAGE_SIZE,
          offset,
        });
        setBooks(append ? (prev) => [...prev, ...data.items] : data.items);
        setBooksTotal(data.total);
      } catch {
        // ignore
      } finally {
        setBooksLoading(false);
      }
    },
    [period, genre, language, sort, activeTab],
  );

  const fetchAuthors = useCallback(
    async (offset = 0, append = false) => {
      setAuthorsLoading(true);
      try {
        const data = await leaderboardApi.listAuthors({ period, limit: PAGE_SIZE, offset });
        setAuthors(append ? (prev) => [...prev, ...data.items] : data.items);
        setAuthorsTotal(data.total);
      } catch {
        // ignore
      } finally {
        setAuthorsLoading(false);
      }
    },
    [period],
  );

  const fetchTranslators = useCallback(
    async (offset = 0, append = false) => {
      setTranslatorsLoading(true);
      try {
        const data = await leaderboardApi.listTranslators({ period, limit: PAGE_SIZE, offset });
        setTranslators(append ? (prev) => [...prev, ...data.items] : data.items);
        setTranslatorsTotal(data.total);
      } catch {
        // ignore
      } finally {
        setTranslatorsLoading(false);
      }
    },
    [period],
  );

  // ── Effects ─────────────────────────────────────────────────────────────

  // Fetch data when tab/filters change
  useEffect(() => {
    if (activeTab === 'books' || activeTab === 'trending') {
      fetchBooks(0);
    } else if (activeTab === 'authors') {
      fetchAuthors(0);
    } else if (activeTab === 'translators') {
      fetchTranslators(0);
    }
  }, [activeTab, fetchBooks, fetchAuthors, fetchTranslators]);

  // Fetch quick-stats previews (authors + translators) on books tab
  useEffect(() => {
    if (activeTab === 'books') {
      leaderboardApi.listAuthors({ period, limit: 3 }).then((d) => setPreviewAuthors(d.items)).catch(() => {});
      leaderboardApi.listTranslators({ period, limit: 3 }).then((d) => setPreviewTranslators(d.items)).catch(() => {});
    }
  }, [activeTab, period]);

  // Reset filters when switching tabs
  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab);
    setSort('');
    if (tab !== 'books' && tab !== 'trending') {
      setGenre('');
      setLanguage('');
    }
  };

  const showFilters = activeTab === 'books' || activeTab === 'trending';
  const showPodium = (activeTab === 'books' || activeTab === 'trending') && books.length >= 3;
  const isLoading =
    activeTab === 'books' || activeTab === 'trending'
      ? booksLoading
      : activeTab === 'authors'
        ? authorsLoading
        : translatorsLoading;

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('title')}
        subtitle={t('subtitle')}
        actions={<PeriodSelector value={period} onChange={setPeriod} />}
        tabs={
          <div className="flex gap-0 border-b -mx-6 px-6 lg:-mx-10 lg:px-10">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.key}
                  onClick={() => handleTabChange(tab.key)}
                  className={cn(
                    'border-b-2 px-4 py-2.5 text-[13px] font-medium transition-colors',
                    activeTab === tab.key
                      ? 'border-primary text-primary'
                      : 'border-transparent text-muted-foreground hover:text-foreground',
                  )}
                >
                  <Icon className="mr-1 inline-block h-3.5 w-3.5" style={{ verticalAlign: '-2px' }} />
                  {t(tab.labelKey)}
                </button>
              );
            })}
          </div>
        }
      />

      {/* Filters */}
      {showFilters && (
        <FilterChips
          genre={genre}
          language={language}
          onGenreChange={setGenre}
          onLanguageChange={setLanguage}
        />
      )}

      {/* Loading skeleton */}
      {isLoading && books.length === 0 && authors.length === 0 && translators.length === 0 && (
        <div className="space-y-4">
          <Skeleton className="h-48 w-full rounded-lg" />
          <Skeleton className="h-64 w-full rounded-lg" />
        </div>
      )}

      {/* Books / Trending tab */}
      {(activeTab === 'books' || activeTab === 'trending') && !isLoading && books.length === 0 && (
        <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
          {t('ranking.noResults')}
        </div>
      )}

      {(activeTab === 'books' || activeTab === 'trending') && books.length > 0 && (
        <div className="space-y-4">
          {showPodium && <Podium books={books.slice(0, 3)} />}

          <RankingList
            books={books}
            sort={sort}
            onSortChange={setSort}
            hasMore={books.length < booksTotal}
            onLoadMore={() => fetchBooks(books.length, true)}
            loading={booksLoading}
          />

          {activeTab === 'books' && (
            <QuickStatsCards
              authors={previewAuthors}
              translators={previewTranslators}
              onViewAuthors={() => handleTabChange('authors')}
              onViewTranslators={() => handleTabChange('translators')}
            />
          )}
        </div>
      )}

      {/* Authors tab */}
      {activeTab === 'authors' && authors.length > 0 && (
        <AuthorList
          authors={authors}
          hasMore={authors.length < authorsTotal}
          onLoadMore={() => fetchAuthors(authors.length, true)}
          loading={authorsLoading}
        />
      )}
      {activeTab === 'authors' && !authorsLoading && authors.length === 0 && (
        <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
          {t('ranking.noResults')}
        </div>
      )}

      {/* Translators tab */}
      {activeTab === 'translators' && translators.length > 0 && (
        <TranslatorList
          translators={translators}
          hasMore={translators.length < translatorsTotal}
          onLoadMore={() => fetchTranslators(translators.length, true)}
          loading={translatorsLoading}
        />
      )}
      {activeTab === 'translators' && !translatorsLoading && translators.length === 0 && (
        <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
          {t('ranking.noResults')}
        </div>
      )}
    </div>
  );
}
