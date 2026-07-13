type Props = {
  progress: number;
  label?: string;
};

export default function TaskProgressBar({ progress, label = "Matching in progress" }: Props) {
  const pct = Math.min(100, Math.max(0, progress));
  return (
    <div className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
      <p>
        {label}… {pct}%
      </p>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-amber-100 dark:bg-amber-900/50">
        <div className="h-full rounded-full bg-amber-500 transition-all duration-300" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
