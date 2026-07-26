// MCP fan-out (C-NAV) — the nav-scope seam. An embedding surface (the Writing Studio's
// Compose panel) can provide an interceptor that remaps a `ui_*` nav tool into a
// surface-internal action INSTEAD of an SPA navigation. Without one, useUiToolExecutor
// falls through to the generic resolveUiTool (router navigate).
//
// Why this exists (live-caught, #12 M-E gate): the generic executor is mounted inside the
// studio Compose panel. When the agent called ui_open_book on the book it was already
// working in, the executor navigated the SPA to /books/{id} — unmounting the ENTIRE studio
// (dock, editor, the compose surface itself) and orphaning the agent's own resumed run
// (its final response was never seen). A nav tool must never destroy the surface that is
// executing it.
import { createContext, useContext } from 'react';
import type { UiNavResolution } from './uiNav';

/** An interceptor's resolution: like UiNavResolution, plus an optional surface-internal
 *  side effect to run instead of navigating (path stays null in that case). */
export interface UiNavInterception extends UiNavResolution {
  effect?: () => void;
}

/** Return an interception to claim the call, or null to fall through to the
 *  generic router-navigation resolution. */
export type UiNavInterceptor = (
  tool: string,
  args: Record<string, unknown>,
) => UiNavInterception | null;

export const UiNavInterceptorContext = createContext<UiNavInterceptor | null>(null);

export function useUiNavInterceptor(): UiNavInterceptor | null {
  return useContext(UiNavInterceptorContext);
}
