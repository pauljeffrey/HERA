"use client";

import { useEffect, useState } from "react";

import { fetchRandomPatient, type PatientBiodata } from "@/lib/api";

const SPIN_FRAMES = ["🧑‍⚕️", "🩺", "📋", "💊", "🫀"];

type Props = {
  embedded?: boolean;
  inSidebar?: boolean;
  defaultOpen?: boolean;
  onUsePatient?: (patient: PatientBiodata) => void;
};

export default function PatientRoulette({
  embedded = false,
  inSidebar = false,
  defaultOpen = false,
  onUsePatient,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const [spinning, setSpinning] = useState(false);
  const [frame, setFrame] = useState(0);
  const [picked, setPicked] = useState<PatientBiodata | null>(null);
  const [totalPatients, setTotalPatients] = useState(0);
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
      const data = await fetchRandomPatient();
      setTotalPatients(data.total_patients);
      if (data.patient) setPicked(data.patient);
      else setError("No patients found in the database.");
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setSpinning(false);
    }
  }

  function usePatient() {
    if (!picked) return;
    onUsePatient?.(picked);
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
        <div className="flex flex-wrap items-center gap-3">
          <div
            className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-2xl ${
              spinning ? "animate-pulse bg-emerald-100" : "bg-white dark:bg-slate-800"
            }`}
          >
            {spinning ? SPIN_FRAMES[frame] : picked ? "✓" : "?"}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
              Explore a patient? Draw someone at random from the synthetic cohort
              {totalPatients ? ` (${totalPatients.toLocaleString()} total)` : ""}.
            </p>
          </div>
          <button
            type="button"
            disabled={spinning}
            onClick={spin}
            className="shrink-0 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
          >
            {spinning ? "Drawing…" : "Draw patient"}
          </button>
        </div>

        {picked ? (
          <div className="mt-4 rounded-xl border border-emerald-200 bg-white p-4 dark:border-emerald-900 dark:bg-slate-950/60">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-base font-semibold text-slate-900 dark:text-slate-100">{picked.name}</p>
                <p className="mt-1 font-mono text-xs text-emerald-700">{picked.patient_id}</p>
              </div>
              <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-800">
                {picked.encounter_count} encounter{picked.encounter_count === 1 ? "" : "s"}
              </span>
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Age</dt>
                <dd className="font-medium text-slate-800 dark:text-slate-100">{picked.age}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Sex</dt>
                <dd className="font-medium text-slate-800 dark:text-slate-100">{picked.sex}</dd>
              </div>
              {picked.specialty_label ? (
                <div className="col-span-2">
                  <dt className="text-xs uppercase tracking-wide text-slate-500">Specialty</dt>
                  <dd className="font-medium text-slate-800 dark:text-slate-100">{picked.specialty_label}</dd>
                </div>
              ) : null}
            </dl>
            <button
              type="button"
              onClick={usePatient}
              className="mt-4 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 dark:bg-emerald-700 dark:hover:bg-emerald-600"
            >
              Discuss this patient
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
          <span className="text-sm font-medium text-slate-800 dark:text-slate-100">Patient roulette</span>
          <span className="text-xs text-slate-500">{open ? "Hide" : "Show"}</span>
        </button>
        {open ? <div className={inSidebar ? "px-3 pb-3" : undefined}>{panel}</div> : null}
      </section>
    );
  }

  return panel;
}

function friendlyError(err: unknown) {
  if (!(err instanceof Error)) return "Could not draw a patient. Try again.";
  if (/failed to fetch|network/i.test(err.message)) {
    return "Could not reach the server. Make sure the backend is running.";
  }
  return "Could not draw a patient. Try again.";
}
