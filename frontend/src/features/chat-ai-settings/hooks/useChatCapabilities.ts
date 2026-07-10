// D-WS4C-EFFECTIVE-VALUE — fetch the deploy-tier capability ceilings once so a
// consumer can render the HONEST effective value of a ceiling'd capability
// (`effective = deploy_allows && userKnob`) instead of a toggle that silently
// does nothing when a deployment kill-switches the capability off.
//
// Self-contained (own state + fetch + cleanup, per the frontend hook rule). The
// fetch is a mount-time synchronization, so useEffect is the right tool. On any
// failure `capabilities` stays null — a consumer treats "unknown" as "assume
// allowed" (the ceiling defaults on), so a transient outage never fabricates a
// scary "disabled by deployment" warning on a capability that actually works.
import { useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { aiSettingsApi } from '../api';
import type { ChatCapabilities } from '../types';

export function useChatCapabilities(): {
  capabilities: ChatCapabilities | null;
  loading: boolean;
} {
  const { accessToken } = useAuth();
  const [capabilities, setCapabilities] = useState<ChatCapabilities | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    let alive = true;
    setLoading(true);
    aiSettingsApi
      .getCapabilities(accessToken)
      .then((c) => {
        if (alive) setCapabilities(c);
      })
      .catch(() => {
        if (alive) setCapabilities(null);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [accessToken]);

  return { capabilities, loading };
}
