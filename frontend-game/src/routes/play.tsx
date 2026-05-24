import { PhaserGame } from '@/components/PhaserGame';
import { HpBar, ManaBar } from '@/components/hud';
import { Sidebar } from '@/components/sidebar/Sidebar';
import { Modal } from '@/components/modal/Modal';
import { RotatePrompt } from '@/components/mobile/RotatePrompt';
import { VirtualGamepad } from '@/components/mobile/VirtualGamepad';
import { EchoPanel } from '@/components/echo/EchoPanel';
import { useTilemapHealth } from '@/api/tilemap-client';

// Main play route. Per spec §1 #3 hybrid React+Phaser:
// - <PhaserGame> renders canvas (absolute inset-0)
// - HUD components are React DOM overlays on top
// - Sidebar is a React DOM panel
// - <Modal> renders conditionally based on ui-store
// - <RotatePrompt> overlays on portrait mobile (landscape-lock per §7.3)
// - <VirtualGamepad> overlays on touch devices

export function PlayRoute(): JSX.Element {
  const health = useTilemapHealth();
  return (
    <div className="relative w-screen h-screen overflow-hidden">
      <PhaserGame />

      {/* HUD overlay top-left */}
      <div className="absolute top-4 left-4 flex flex-col gap-2 pointer-events-auto">
        <HpBar />
        <ManaBar />
        <div className="text-xs text-slate-300 font-mono mt-2">
          tilemap-service: {health.isLoading ? '…' : health.data?.status ?? 'down'}
        </div>
      </div>

      {/* Right-side sidebar */}
      <div className="absolute top-0 right-0 h-full">
        <Sidebar />
      </div>

      {/* Session E WS echo demo panel */}
      <EchoPanel />

      {/* Mobile + modal overlays */}
      <VirtualGamepad />
      <Modal>
        <h2 className="text-lg font-semibold mb-2 text-slate-100">Modal placeholder</h2>
        <p className="text-slate-300 text-sm">Session D wires real Settings/Confirm/Dialog content.</p>
      </Modal>
      <RotatePrompt />
    </div>
  );
}
