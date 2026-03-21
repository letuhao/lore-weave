import { useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { PlatformModel, aiModelsApi } from '@/features/ai-models/api';

export function PlatformModelsPage() {
  const { accessToken } = useAuth();
  const [items, setItems] = useState<PlatformModel[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    const run = async () => {
      if (!accessToken) return;
      try {
        const res = await aiModelsApi.listPlatformModels(accessToken);
        setItems(res.items);
      } catch (e) {
        setError((e as Error).message);
      }
    };
    void run();
  }, [accessToken]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Platform models</h1>
        <p className="text-sm text-muted-foreground">Platform model catalog with tier quota + credits overage policy metadata.</p>
      </div>
      <div className="space-y-2">
        {items.map((item) => (
          <div key={item.platform_model_id} className="rounded border p-3 text-sm">
            <p>
              <strong>{item.display_name}</strong> - {item.provider_kind}/{item.provider_model_name}
            </p>
            <p className="text-muted-foreground">Status: {item.status}</p>
          </div>
        ))}
        {items.length === 0 && <p className="text-sm text-muted-foreground">No platform models configured yet.</p>}
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}
