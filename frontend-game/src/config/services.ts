// Service endpoint configuration. Centralized so V1+ wires environment-
// variable injection at build time (Vite VITE_* vars) without hunting
// down hardcoded URLs across the codebase.
//
// V0 defaults assume docker compose --profile full has exposed all
// services on host loopback at the canonical ports. Override per-env
// by setting VITE_TILEMAP_SERVICE_URL / VITE_GAME_SERVER_URL /
// VITE_INTERNAL_TOKEN at build time.
//
// SECURITY: VITE_INTERNAL_TOKEN ships in the client bundle (visible in
// browser DevTools). V0 dev-only token is acceptable; V1+ MUST replace
// with per-user JWT obtained via auth-service login flow.

interface ImportMetaEnvExt {
  readonly VITE_TILEMAP_SERVICE_URL?: string;
  readonly VITE_GAME_SERVER_URL?: string;
  readonly VITE_INTERNAL_TOKEN?: string;
}

const env = (import.meta as { env?: ImportMetaEnvExt }).env ?? {};

export const SERVICES = {
  tilemap: env.VITE_TILEMAP_SERVICE_URL ?? 'http://localhost:8220',
  gameServer: env.VITE_GAME_SERVER_URL ?? 'ws://localhost:2567',
  // V0 dev token — matches services/game-server EchoRoom.onAuth default
  // and infra/docker-compose.yml LOREWEAVE_INTERNAL_TOKEN default. V1
  // replaces with auth-service JWT (see TODO in spec §17).
  devToken: env.VITE_INTERNAL_TOKEN ?? 'dev_internal_token',
} as const;
