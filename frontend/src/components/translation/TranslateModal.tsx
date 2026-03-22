import { useState } from 'react';
import type { BookTranslationSettings, ModelSource, TranslationJob } from '@/features/translation/api';
import { translationApi } from '@/features/translation/api';
import { ModelSelector } from './ModelSelector';
import { LanguagePicker } from '@/components/books/LanguagePicker';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';

type Step = 1 | 2 | 3;

type Props = {
  token: string;
  bookId: string;
  chapterIds: string[];
  settings: BookTranslationSettings;
  onClose: () => void;
  onJobCreated: (job: TranslationJob) => void;
};

export function TranslateModal({ token, bookId, chapterIds, settings, onClose, onJobCreated }: Props) {
  const [step, setStep] = useState<Step>(1);
  const [targetLanguage, setTargetLanguage] = useState(settings.target_language || 'vi');
  const [modelSource, setModelSource] = useState<ModelSource>(settings.model_source);
  const [modelRef, setModelRef] = useState<string | null>(settings.model_ref);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit() {
    if (!modelRef) { setError('Please select a model.'); return; }
    setSubmitting(true);
    setError('');
    try {
      // Save settings for this language combination then create job
      await translationApi.putBookSettings(token, bookId, {
        target_language: targetLanguage,
        model_source: modelSource,
        model_ref: modelRef,
        system_prompt: settings.system_prompt,
        user_prompt_tpl: settings.user_prompt_tpl,
        compact_model_source: settings.compact_model_source,
        compact_model_ref: settings.compact_model_ref,
        chunk_size_tokens: settings.chunk_size_tokens,
        invoke_timeout_secs: settings.invoke_timeout_secs,
      });
      const job = await translationApi.createJob(token, bookId, { chapter_ids: chapterIds });
      onJobCreated(job);
    } catch (e) {
      setError((e as Error).message || 'Failed to start translation');
      setStep(3);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-lg border bg-background p-6 shadow-xl">
        {/* Header */}
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-semibold">Translate chapters</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">✕</button>
        </div>

        {/* Step indicator */}
        <p className="mb-4 text-xs text-muted-foreground">Step {step} of 3</p>

        {/* Step 1 — Target language */}
        {step === 1 && (
          <div className="space-y-4">
            <LanguagePicker
              label="Target language"
              value={targetLanguage}
              onChange={setTargetLanguage}
            />
            <div className="flex justify-end">
              <Button onClick={() => setStep(2)} disabled={!targetLanguage}>
                Next →
              </Button>
            </div>
          </div>
        )}

        {/* Step 2 — Model */}
        {step === 2 && (
          <div className="space-y-4">
            <ModelSelector
              token={token}
              value={{ model_source: modelSource, model_ref: modelRef }}
              onChange={(v) => { setModelSource(v.model_source); setModelRef(v.model_ref); }}
            />
            <div className="flex justify-between">
              <Button variant="outline" onClick={() => setStep(1)}>← Back</Button>
              <Button onClick={() => setStep(3)} disabled={!modelRef}>Next →</Button>
            </div>
          </div>
        )}

        {/* Step 3 — Review */}
        {step === 3 && (
          <div className="space-y-4">
            <div className="rounded border bg-muted p-3 text-sm space-y-1">
              <p><span className="font-medium">Chapters:</span> {chapterIds.length}</p>
              <p><span className="font-medium">Target language:</span> {targetLanguage}</p>
              <p><span className="font-medium">Model:</span> {modelSource} / {modelRef ?? '—'}</p>
            </div>
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <div className="flex justify-between">
              <Button variant="outline" onClick={() => setStep(2)}>← Back</Button>
              <Button onClick={handleSubmit} disabled={submitting}>
                {submitting ? 'Starting…' : 'Start translation'}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
