interface UserMessageProps {
  content: string;
}

export function UserMessage({ content }: UserMessageProps) {
  return (
    <p className="whitespace-pre-wrap text-sm leading-relaxed">{content}</p>
  );
}
