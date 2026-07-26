import { apiJson } from '@/api';

// P5 public-MCP OAuth 2.1 consent. The auth-service `/oauth/authorize` endpoint
// validates the request and redirects the browser here with the request params on
// the query string; the user approves a (possibly downscoped) grant, and we POST
// it to `/v1/account/oauth/consent` (Bearer JWT). The server mints a single-use
// auth code and returns the client's redirect_uri with `?code=…&state=…`.
// See services/auth-service/internal/api/oauth_flow.go.

/** The validated authorize params the AS forwards to the consent page. */
export type ConsentParams = {
  clientId: string;
  clientName: string; // display-only; forwarded by the AS for the consent screen
  redirectUri: string;
  scope: string; // space-separated, includes `domain:<d>` tokens
  state: string;
  codeChallenge: string;
  codeChallengeMethod: string;
  resource: string;
};

export type ConsentRequest = {
  action?: 'approve' | 'deny'; // omitted = approve
  client_id: string;
  redirect_uri: string;
  granted_scopes: string[]; // the downscoped subset the user approved
  requested_scopes: string[]; // the full set the client asked for
  code_challenge: string;
  code_challenge_method: string;
  resource: string;
  state: string;
};

export const oauthApi = {
  /** Approve a downscoped grant → returns the client redirect_uri carrying the code. */
  consent(token: string, payload: ConsentRequest) {
    return apiJson<{ redirect_uri: string }>('/v1/account/oauth/consent', {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },
};
