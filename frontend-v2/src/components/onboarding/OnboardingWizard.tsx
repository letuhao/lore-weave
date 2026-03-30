import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, Key, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';

const STORAGE_KEY = 'lw_onboarding_done';

export function useOnboarding() {
  const done = localStorage.getItem(STORAGE_KEY) === '1';
  const markDone = () => localStorage.setItem(STORAGE_KEY, '1');
  return { showOnboarding: !done, markDone };
}

export function OnboardingWizard({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(0);
  const navigate = useNavigate();

  const steps = [
    {
      icon: Sparkles,
      title: 'Welcome to LoreWeave',
      description: 'A multilingual novel platform for writing, translating, and building story worlds with AI assistance.',
    },
    {
      icon: Key,
      title: 'Configure AI Models',
      description: 'Add your API keys in Settings → Model Providers to enable AI translation and chat features. You can skip this and add them later.',
      action: { label: 'Go to Settings', onClick: () => { onClose(); navigate('/settings/providers'); } },
    },
    {
      icon: BookOpen,
      title: 'Create Your First Book',
      description: 'Start by creating a book, then add chapters. You can write directly or upload .txt files.',
      action: { label: 'Create Book', onClick: () => { onClose(); navigate('/books'); } },
    },
  ];

  const current = steps[step];
  const Icon = current.icon;

  const finish = () => {
    localStorage.setItem(STORAGE_KEY, '1');
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md rounded-lg border bg-background p-8 shadow-xl">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-primary/15">
            <Icon className="h-6 w-6 text-primary" />
          </div>
          <h2 className="font-serif text-lg font-semibold">{current.title}</h2>
          <p className="mt-2 text-sm text-muted-foreground">{current.description}</p>
        </div>

        {/* Progress dots */}
        <div className="mb-6 flex justify-center gap-2">
          {steps.map((_, i) => (
            <div key={i} className={cn('h-1.5 w-1.5 rounded-full', i === step ? 'bg-primary' : 'bg-secondary')} />
          ))}
        </div>

        <div className="flex items-center justify-between">
          <button onClick={finish} className="text-xs text-muted-foreground hover:text-foreground">Skip</button>
          <div className="flex gap-2">
            {current.action && (
              <button onClick={current.action.onClick} className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-secondary">
                {current.action.label}
              </button>
            )}
            {step < steps.length - 1 ? (
              <button onClick={() => setStep(step + 1)} className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90">
                Next
              </button>
            ) : (
              <button onClick={finish} className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90">
                Get Started
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
