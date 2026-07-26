import { useOAuthConsent } from '@/features/oauth/hooks/useOAuthConsent';
import { OAuthConsentView } from '@/features/oauth/components/OAuthConsentView';

/**
 * P5 public-MCP OAuth consent page (route `/oauth/consent`). The auth-service
 * `/oauth/authorize` endpoint redirects the browser here after validating the
 * request. NOT wrapped in RequireAuth — the hook handles the unauthenticated case
 * itself so the full consent URL (query string included) survives the login round-trip.
 */
export function OAuthConsentPage() {
  const consent = useOAuthConsent();
  return <OAuthConsentView {...consent} />;
}
