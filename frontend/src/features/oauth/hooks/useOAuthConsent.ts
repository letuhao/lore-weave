import { useCallback, useMemo, useState } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/auth';
import { splitScopes } from '@/features/settings/api';
import { oauthApi, type ConsentParams } from '../api';

/**
 * Controller for the OAuth consent page. Reads the validated authorize params off
 * the query string, owns the per-scope grant toggles (the user may only NARROW the
 * request), and drives approve/deny. Approve POSTs the downscoped grant and follows
 * the returned client redirect_uri; deny bounces back to the client with
 * `error=access_denied` per OAuth.
 */
export function useOAuthConsent() {
  const [sp] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { accessToken, user } = useAuth();

  const params: ConsentParams = useMemo(
    () => ({
      clientId: sp.get('client_id') ?? '',
      clientName: sp.get('client_name') ?? '',
      redirectUri: sp.get('redirect_uri') ?? '',
      scope: sp.get('scope') ?? '',
      state: sp.get('state') ?? '',
      codeChallenge: sp.get('code_challenge') ?? '',
      codeChallengeMethod: sp.get('code_challenge_method') ?? '',
      resource: sp.get('resource') ?? '',
    }),
    [sp],
  );

  // The full set of scope tokens the client requested (tier + `domain:<d>`), in the
  // order they arrived. PKCE S256 + resource are required for a well-formed request.
  const requestedTokens = useMemo(
    () => params.scope.split(/\s+/).filter((s) => s && s !== '*'),
    [params.scope],
  );
  const { tiers, domains } = useMemo(() => splitScopes(requestedTokens), [requestedTokens]);

  // The host the client will redirect back to. Under open DCR the `client_name` is
  // attacker-controlled, so we surface the registered redirect_uri host (which the
  // user can actually judge) plus an "unverified app" hint before they approve.
  const redirectHost = useMemo(() => {
    try {
      return new URL(params.redirectUri).host;
    } catch {
      return '';
    }
  }, [params.redirectUri]);

  const valid =
    !!params.clientId &&
    !!params.redirectUri &&
    requestedTokens.length > 0 &&
    !!params.codeChallenge &&
    params.codeChallengeMethod === 'S256' &&
    !!params.resource;

  // Grant toggles — start with everything the client asked for enabled.
  const [granted, setGranted] = useState<Set<string>>(() => new Set(requestedTokens));
  const toggle = useCallback((token: string) => {
    setGranted((prev) => {
      const next = new Set(prev);
      if (next.has(token)) next.delete(token);
      else next.add(token);
      return next;
    });
  }, []);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Not logged in → send to login, preserving the FULL consent URL (query included,
  // which RequireAuth would drop) so we return here after sign-in.
  const needsLogin = !accessToken;
  const goLogin = useCallback(() => {
    navigate('/login', { state: { from: location.pathname + location.search }, replace: true });
  }, [navigate, location.pathname, location.search]);

  const approve = useCallback(async () => {
    if (!accessToken || !valid) return;
    const grantedScopes = Array.from(granted);
    if (grantedScopes.length === 0) {
      setError('no_scopes');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await oauthApi.consent(accessToken, {
        client_id: params.clientId,
        redirect_uri: params.redirectUri,
        granted_scopes: grantedScopes,
        requested_scopes: requestedTokens,
        code_challenge: params.codeChallenge,
        code_challenge_method: params.codeChallengeMethod,
        resource: params.resource,
        state: params.state,
      });
      // Leaving the SPA — the redirect target is the external OAuth client.
      window.location.assign(res.redirect_uri);
    } catch {
      setError('error');
      setSubmitting(false);
    }
  }, [accessToken, valid, granted, params, requestedTokens]);

  // Deny → POST action:"deny" so the BACKEND validates redirect_uri (registered for
  // the client) before bouncing with error=access_denied. We never build the redirect
  // client-side from the raw query string — that would be an open redirect on a direct
  // link with an attacker-supplied, unregistered redirect_uri.
  const deny = useCallback(async () => {
    if (!accessToken || !params.redirectUri) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await oauthApi.consent(accessToken, {
        action: 'deny',
        client_id: params.clientId,
        redirect_uri: params.redirectUri,
        granted_scopes: [],
        requested_scopes: requestedTokens,
        code_challenge: params.codeChallenge,
        code_challenge_method: params.codeChallengeMethod,
        resource: params.resource,
        state: params.state,
      });
      window.location.assign(res.redirect_uri);
    } catch {
      setError('error');
      setSubmitting(false);
    }
  }, [accessToken, params, requestedTokens]);

  return {
    params,
    redirectHost,
    tiers,
    domains,
    granted,
    toggle,
    valid,
    needsLogin,
    goLogin,
    approve,
    deny,
    submitting,
    error,
    userEmail: user?.email ?? null,
  };
}
