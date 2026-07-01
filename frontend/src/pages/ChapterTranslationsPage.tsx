import { useParams, useSearchParams } from 'react-router-dom';
import { ChapterTranslationsPanel } from '@/features/translation/components/ChapterTranslationsPanel';

/**
 * Standalone per-chapter translation route.
 *
 * Thin wrapper over ChapterTranslationsPanel (the same workspace the editor's Translate
 * workmode embeds). Seeds the panel's selection from the `?lang=` / `?vid=` deep-link
 * (used by the translation matrix) so a translated cell still opens straight to that
 * language.
 */
export function ChapterTranslationsPage() {
  const { bookId = '', chapterId = '' } = useParams();
  const [searchParams] = useSearchParams();

  return (
    <ChapterTranslationsPanel
      bookId={bookId}
      chapterId={chapterId}
      initialLang={searchParams.get('lang')}
      initialVersionId={searchParams.get('vid')}
      showBreadcrumb
    />
  );
}
