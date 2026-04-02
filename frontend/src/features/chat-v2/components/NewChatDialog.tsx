import { useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { Button } from '@/components/ui/button';
import {
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Select } from '@/components/ui/select';
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
    <DialogContent className="max-w-sm" onClose={onClose}>
      <DialogHeader>
        <DialogTitle>Start New Chat</DialogTitle>
      </DialogHeader>
      <div className="space-y-4 py-2">
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">Model</label>
          {loading ? (
            <div className="h-9 animate-pulse rounded-md bg-muted" />
          ) : userModels.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No active models. Add one in Settings &rarr; Providers.
            </p>
          ) : (
            <Select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="h-8 text-sm"
            >
              {userModels.map((m) => (
                <option key={m.user_model_id} value={m.user_model_id}>
                  {m.alias ?? m.provider_model_name} ({m.provider_kind})
                </option>
              ))}
            </Select>
          )}
        </div>
        <Button
          className="w-full"
          disabled={!selectedModel || loading}
          onClick={() => onCreate(selectedModel)}
        >
          Start Chat
        </Button>
      </div>
    </DialogContent>
  );
}
