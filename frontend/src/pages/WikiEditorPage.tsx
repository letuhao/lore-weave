// 15_wiki_panels.md B5 — thin page shell over the shared WikiEditorWorkspace (DOCK-2 "no
// fork"). The classic route has no params-retargeting concern (a route change always fully
// remounts this component), so it plugs straight into `onBack` with a plain navigate — the
// dirty-guard on that navigate lives inside WikiEditorWorkspace itself (B2b), shared with the
// studio's `wiki-editor` panel.
import { useParams, useNavigate } from 'react-router-dom';
import { WikiEditorWorkspace } from '@/features/wiki/components/WikiEditorWorkspace';

export function WikiEditorPage() {
  const { bookId = '', articleId = '' } = useParams();
  const navigate = useNavigate();

  return (
    <WikiEditorWorkspace
      bookId={bookId}
      articleId={articleId}
      onBack={() => navigate(`/books/${bookId}/wiki`)}
    />
  );
}
