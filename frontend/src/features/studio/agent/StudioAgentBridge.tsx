// The studio ↔ agent bridge — a headless component mounted INSIDE the chat provider tree (via the
// Compose panel's actionBar slot, which Chat renders inside its providers). Runs both agent→GUI
// lanes that need the live chat stream:
//   • Lane A (#09) — resolve studio ui_* tools (open panel / focus manuscript unit) via the host.
//   • Lane B (#09) — reconcile completed MCP writes → refresh the GUI (code, not LLM blobs).
// Renders nothing.
import { useStudioUiToolExecutor } from './useStudioUiToolExecutor';
import { useStudioEffectReconciler } from './useStudioEffectReconciler';

export function StudioAgentBridge(): null {
  useStudioUiToolExecutor();
  useStudioEffectReconciler();
  return null;
}
