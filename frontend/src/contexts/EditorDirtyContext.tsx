import { createContext, useContext, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

interface EditorDirtyContextValue {
  isDirty: boolean;
  setIsDirty: (dirty: boolean) => void;
  pendingNavigation: string | null;
  guardedNavigate: (to: string) => void;
  confirmNavigation: () => void;
  cancelNavigation: () => void;
}

const EditorDirtyContext = createContext<EditorDirtyContextValue>({
  isDirty: false,
  setIsDirty: () => {},
  pendingNavigation: null,
  guardedNavigate: () => {},
  confirmNavigation: () => {},
  cancelNavigation: () => {},
});

export function EditorDirtyProvider({ children }: { children: ReactNode }) {
  const [isDirty, setIsDirty] = useState(false);
  const [pendingNavigation, setPendingNavigation] = useState<string | null>(null);
  const navigate = useNavigate();

  const guardedNavigate = (to: string) => {
    if (isDirty) {
      setPendingNavigation(to);
    } else {
      navigate(to);
    }
  };

  const confirmNavigation = () => {
    if (pendingNavigation) {
      navigate(pendingNavigation);
      setPendingNavigation(null);
    }
  };

  const cancelNavigation = () => setPendingNavigation(null);

  return (
    <EditorDirtyContext.Provider
      value={{ isDirty, setIsDirty, pendingNavigation, guardedNavigate, confirmNavigation, cancelNavigation }}
    >
      {children}
    </EditorDirtyContext.Provider>
  );
}

export function useEditorDirty() {
  return useContext(EditorDirtyContext);
}
