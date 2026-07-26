import { useTranslation } from 'react-i18next';
import { ModelPicker } from '@/components/model-picker/ModelPicker';

interface StepConfigureProps {
  pageCount: number;
  pagesPerChunk: number;
  captionImages: boolean;
  modelRef: string | null;
  onPagesPerChunkChange: (n: number) => void;
  onCaptionImagesChange: (v: boolean) => void;
  onModelChange: (modelSource: string | null, modelRef: string | null) => void;
}

// Soft warning only (spec L8 — no hard cap). A very high chapter count is
// unusual, not invalid — the user may still proceed.
const HIGH_CHAPTER_COUNT_WARNING_THRESHOLD = 300;

export function StepConfigure({
  pageCount,
  pagesPerChunk,
  captionImages,
  modelRef,
  onPagesPerChunkChange,
  onCaptionImagesChange,
  onModelChange,
}: StepConfigureProps) {
  const { t } = useTranslation('pdf-import');
  const chapterCount = Math.ceil(pageCount / Math.max(1, pagesPerChunk));

  return (
    <div className="space-y-4">
      <div>
        <label className="text-xs font-medium mb-1 block">{t('configure.pagesPerChunk')}</label>
        <input
          type="number"
          min={1}
          value={pagesPerChunk}
          onChange={(e) => onPagesPerChunkChange(Number(e.target.value))}
          className="w-24 rounded-md border bg-background px-2.5 py-1.5 text-sm"
        />
        <p className="text-[11px] text-muted-foreground mt-1">{t('configure.pagesPerChunkHint')}</p>
      </div>

      <div className="rounded-md border bg-card/50 p-3 text-xs">
        {t('configure.willCreate', { count: chapterCount, pages: pageCount })}
        {chapterCount > HIGH_CHAPTER_COUNT_WARNING_THRESHOLD && (
          <p className="mt-1 text-amber-500">{t('configure.highChapterWarning')}</p>
        )}
      </div>

      <div className="flex items-center justify-between rounded-md border p-3">
        <div>
          <p className="text-xs font-medium">{t('configure.captionImages')}</p>
          <p className="text-[11px] text-muted-foreground">{t('configure.captionImagesHint')}</p>
        </div>
        <input
          type="checkbox"
          checked={captionImages}
          onChange={(e) => onCaptionImagesChange(e.target.checked)}
          className="h-4 w-4"
        />
      </div>

      {captionImages && (
        <div>
          <label className="text-xs font-medium mb-1 block">{t('configure.visionModel')}</label>
          <ModelPicker
            capability="chat"
            value={modelRef}
            onChange={(userModelId) => onModelChange(userModelId ? 'user_model' : null, userModelId)}
            placeholder={t('configure.visionModelPlaceholder')}
            ariaLabel={t('configure.visionModelAriaLabel')}
          />
          <p className="text-[11px] text-muted-foreground mt-1">{t('configure.visionModelHint')}</p>
        </div>
      )}
    </div>
  );
}
