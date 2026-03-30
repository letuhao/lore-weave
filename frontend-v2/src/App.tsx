import { BrowserRouter, Routes, Route } from 'react-router-dom';

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<PlaceholderHome />} />
      </Routes>
    </BrowserRouter>
  );
}

function PlaceholderHome() {
  return (
    <div className="flex h-screen items-center justify-center bg-background text-foreground">
      <div className="text-center space-y-4">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-lg bg-primary text-primary-foreground text-lg font-bold">
          L
        </div>
        <h1 className="font-serif text-2xl font-semibold">LoreWeave v2</h1>
        <p className="text-sm text-muted-foreground">Scaffold ready. Phase 1 in progress.</p>
      </div>
    </div>
  );
}
