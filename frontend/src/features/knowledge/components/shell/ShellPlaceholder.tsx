// C6 (G6) — placeholder for project-detail shell sub-tabs whose CONTENT
// lands in later cycles (Proposals → C11, Gap → C10, graph → C5/C19).
// The SHELL + scoping is this cycle's deliverable; the content is not.
export function ShellPlaceholder({ message }: { message: string }) {
  return (
    <p
      className="rounded-md border border-dashed px-3 py-10 text-center text-[12px] text-muted-foreground"
      data-testid="shell-placeholder"
    >
      {message}
    </p>
  );
}
