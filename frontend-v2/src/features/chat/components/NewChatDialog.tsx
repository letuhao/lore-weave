import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { useAuth } from '@/auth';
import { aiModelsApi, type UserModel } from '@/features/ai-models/api';

interface NewChatDialogProps {
  open: boolean;
  onClose: () => void;
  onCreate: (modelRef: string) => void;
}

export function NewChatDialog({ open, onClose, onCreate }: NewChatDialogProps) {
  const { accessToken } = useAuth();
  const [userModels, setUserModels] = useState<UserModel[]>([]);
  const [selectedModel, setSelectedModel] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !accessToken) return;
    setLoading(true);
    void aiModelsApi
      .listUserModels(accessToken, { include_inactive: false })
      .then((res) => {
        setUserModels(res.items);
        if (res.items.length > 0 && !selectedModel) {
          setSelectedModel(res.items[0].user_model_id);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [open, accessToken]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="w-full max-w-sm rounded-lg border bg-card p-5 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold">Start New Chat</h3>
          <button type="button" onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-secondary hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Model</label>
            {loading ? (
              <div className="h-9 animate-pulse rounded-md bg-muted" />
            ) : userModels.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No active models. Add one in Settings &rarr; Providers.
              </p>
            ) : (
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="h-8 w-full rounded-md border bg-input px-2 text-sm text-foreground outline-none focus:border-ring"
              >
                {userModels.map((m) => (
                  <option key={m.user_model_id} value={m.user_model_id}>
                    {m.alias ?? m.provider_model_name} ({m.provider_kind})
                  </option>
                ))}
              </select>
            )}
          </div>
          <button
            type="button"
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:brightness-110 disabled:opacity-50"
            disabled={!selectedModel || loading}
            onClick={() => onCreate(selectedModel)}
          >
            Start Chat
          </button>
        </div>
      </div>
    </div>
  );
}
