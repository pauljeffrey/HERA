"use client";

import { useEffect, useState } from "react";

import { fetchRandomCriterion, type CriteriaPrompt } from "@/lib/api";

const SPIN_FRAMES = ["🎲", "🧬", "📋", "🔬", "⚕️"];

type Props = {
  embedded?: boolean;
  inSidebar?: boolean;
  defaultOpen?: boolean;
  onUseCriterion?: (text: string) => void;
};

export default function CriteriaRoulette({
  embedded = false,
  inSidebar = false,
  defaultOpen = false,
  onUseCriterion,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const [spinning, setSpinning] = useState(false);
  const [frame, setFrame] = useState(0);
  const [picked, setPicked] = useState<CriteriaPrompt | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!spinning) return;
    const timer = setInterval(() => setFrame((value) => (value + 1) % SPIN_FRAMES.length), 120);
    return () => clearInterval(timer);
  }, [spinning]);

  async function spin() {
    setSpinning(true);
    setError(null);
    try {
      await new Promise((resolve) => setTimeout(resolve, 700));
      const data = await fetchRandomCriterion();
      if (data.criterion) setPicked(data.criterion);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setSpinning(false);
    }
  }

  function useCriterion() {
    if (!picked) return;
    onUseCriterion?.(picked.text);
    if (embedded) setOpen(false);
  }

  const panel = (
    <div className={embedded ? (inSidebar ? "pb-2 pt-1" : "px-4 pb-4 pt-1") : "mx-auto max-w-3xl p-6"}>
      <div
        className={
          embedded
            ? "rounded-xl border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-800 dark:bg-slate-900/50"
            : "rounded-3xl border border-slate-200/60 bg-white/90 p-8 text-center shadow-lg backdrop-blur-md dark:border-slate-800 dark:bg-slate-900/80"
        }
      >
        <div className={inSidebar ? "flex flex-col gap-3" : "flex flex-wrap items-center gap-3"}>
          <div className={inSidebar ? "flex items-start gap-3" : "contents"}>
            <div
              className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-2xl ${
                spinning ? "animate-pulse bg-emerald-100" : "bg-white dark:bg-slate-800"
              }`}
            >
              {spinning ? SPIN_FRAMES[frame] : picked ? "✓" : "?"}
            </div>
            <p className="min-w-0 flex-1 text-sm font-medium leading-snug text-slate-800 dark:text-slate-100">
              Need inspiration? Draw a random trial criterion from the synthetic cohort.
            </p>
          </div>
          <button
            type="button"
            disabled={spinning}
            onClick={spin}
            className={`shrink-0 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50 ${
              inSidebar ? "w-full" : ""
            }`}
          >
            {spinning ? "Drawing…" : "Draw criterion"}
          </button>
        </div>

        {picked ? (
          <div className="mt-4 rounded-xl border border-emerald-200 bg-white p-4 dark:border-emerald-900 dark:bg-slate-950/60">
            <p className="break-words text-sm leading-relaxed text-slate-800 dark:text-slate-100">{picked.text}</p>
            <button
              type="button"
              onClick={useCriterion}
              className={`mt-3 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 dark:bg-emerald-700 dark:hover:bg-emerald-600 ${
                inSidebar ? "w-full" : ""
              }`}
            >
              Use in conversation
            </button>
          </div>
        ) : null}

        {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
      </div>
    </div>
  );

  if (embedded) {
    return (
      <section
        className={
          inSidebar
            ? "rounded-xl border border-slate-200/60 bg-white dark:border-slate-800 dark:bg-slate-900/70"
            : "border-b border-slate-200/70 bg-white/70 dark:border-slate-800 dark:bg-slate-950/40"
        }
      >
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className={`flex w-full items-center justify-between text-left ${inSidebar ? "px-3 py-2.5" : "px-4 py-3"}`}
        >
          <span className="text-sm font-medium text-slate-800 dark:text-slate-100">Criteria roulette</span>
          <span className="text-xs text-slate-500">{open ? "Hide" : "Show"}</span>
        </button>
        {open ? <div className={inSidebar ? "px-3 pb-3" : undefined}>{panel}</div> : null}
      </section>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-emerald-50 to-slate-50 dark:from-slate-950 dark:to-slate-900">
      <header className="border-b border-slate-200/60 bg-white/80 px-6 py-8 backdrop-blur-md dark:border-slate-800">
        <div className="mx-auto max-w-3xl text-center">
          <h1 className="text-3xl font-semibold text-slate-900 dark:text-slate-100">Criteria roulette</h1>
          <p className="mt-2 text-sm text-slate-500">
            Draw a random inclusion or exclusion criterion to practice screening conversations.
          </p>
        </div>
      </header>
      {panel}
    </div>
  );
}

function friendlyError(err: unknown) {
  if (!(err instanceof Error)) return "Could not draw a criterion. Try again.";
  if (/failed to fetch|network/i.test(err.message)) {
    return "Could not reach the server. Make sure the backend is running.";
  }
  return "Could not draw a criterion. Try again.";
}
