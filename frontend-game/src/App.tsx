import { Navigate, Route, Routes } from 'react-router-dom';
import { LoginRoute } from '@/routes/login';
import { WorldSelectRoute } from '@/routes/world-select';
import { PlayRoute } from '@/routes/play';

// App router shell. Per spec §3, three routes:
//   /login         → LoginRoute (Session E wires real auth)
//   /world-select  → WorldSelectRoute (Session E wires character list)
//   /play          → PlayRoute (PhaserGame + HUD overlay, Session D wires real demo)

export default function App(): JSX.Element {
  return (
    <Routes>
      <Route path="/login" element={<LoginRoute />} />
      <Route path="/world-select" element={<WorldSelectRoute />} />
      <Route path="/play" element={<PlayRoute />} />
      <Route path="*" element={<Navigate to="/play" replace />} />
    </Routes>
  );
}
