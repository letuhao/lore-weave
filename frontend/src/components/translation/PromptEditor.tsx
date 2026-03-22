type Props = {
  systemPrompt: string;
  userPromptTpl: string;
  onSystemPromptChange: (v: string) => void;
  onUserPromptTplChange: (v: string) => void;
  disabled?: boolean;
};

export function PromptEditor({
  systemPrompt,
  userPromptTpl,
  onSystemPromptChange,
  onUserPromptTplChange,
  disabled,
}: Props) {
  return (
    <div className="space-y-3">
      <div className="space-y-2">
        <label className="text-sm font-medium">System prompt</label>
        <textarea
          className="w-full rounded border px-2 py-2 text-sm font-mono"
          rows={4}
          value={systemPrompt}
          onChange={(e) => onSystemPromptChange(e.target.value)}
          disabled={disabled}
        />
      </div>
      <div className="space-y-2">
        <label className="text-sm font-medium">User prompt template</label>
        <textarea
          className="w-full rounded border px-2 py-2 text-sm font-mono"
          rows={6}
          value={userPromptTpl}
          onChange={(e) => onUserPromptTplChange(e.target.value)}
          disabled={disabled}
        />
        <p className="text-xs text-muted-foreground">
          Variables: {'{source_language}'}, {'{target_language}'}, {'{chapter_text}'}
        </p>
      </div>
    </div>
  );
}
