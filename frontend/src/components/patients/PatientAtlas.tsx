"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import PatientLookupSidebar from "@/components/patients/PatientLookupSidebar";
import { fetchPatient, fetchPatients, type PatientSnapshot } from "@/lib/api";

type PatientCard = {
  id: string;
  snapshot?: PatientSnapshot;
};

export default function PatientAtlas() {
  const [cards, setCards] = useState<PatientCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchPatients()
      .then(async (ids) => {
        const snapshots = await Promise.all(
          ids.map(async (id) => {
            try {
              const snapshot = await fetchPatient(id);
              return { id, snapshot };
            } catch {
              return { id };
            }
          }),
        );
        setCards(snapshots);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <header className="border-b border-slate-200/60 bg-white/80 px-6 py-8 backdrop-blur-md dark:border-slate-800">
        <div className="mx-auto max-w-7xl">
          <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">Synthetic Cohort</p>
          <h1 className="text-3xl font-semibold text-slate-900 dark:text-slate-100">Patient Atlas</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-500">
            Browse demo EHR snapshots before dispatching trial matches. Use the patient lookup panel to pull
            encounters, labs, and investigations by ID while you chat in the Command Center.
          </p>
        </div>
      </header>

      <div className="mx-auto flex max-w-7xl flex-col lg:flex-row">
        <PatientLookupSidebar />

        <div className="min-w-0 flex-1 p-6">
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          {loading ? <p className="text-sm text-slate-500">Loading patient snapshots…</p> : null}

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {cards.map(({ id, snapshot }) => {
            const eligible = snapshot?.audit_payload.selected_patients.find((p) => p.patient_id === id);
            const encounterCount = snapshot?.encounters.length ?? 0;
            const featureCount = snapshot?.extracted_features.length ?? 0;

            return (
              <Link
                key={id}
                href={`/patients/${id}`}
                className="group rounded-2xl border border-slate-200/60 bg-white/80 p-5 shadow-sm backdrop-blur-md transition hover:-translate-y-0.5 hover:border-emerald-400 hover:shadow-md dark:border-slate-800 dark:bg-slate-900/70"
              >
                <div className="mb-4 flex items-start justify-between gap-2">
                  <div>
                    <p className="text-lg font-semibold text-slate-900 dark:text-slate-100">{id}</p>
                    <p className="text-xs text-slate-500">{snapshot?.trial_id ?? "TRIAL-HF-2026-001"}</p>
                  </div>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      eligible?.overall_eligible
                        ? "bg-emerald-100 text-emerald-800"
                        : "bg-amber-100 text-amber-800"
                    }`}
                  >
                    {eligible?.overall_eligible ? "Eligible" : "Review"}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 text-center">
                  <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/50">
                    <p className="text-2xl font-semibold text-emerald-700">{encounterCount}</p>
                    <p className="text-xs text-slate-500">Encounters</p>
                  </div>
                  <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/50">
                    <p className="text-2xl font-semibold text-emerald-700">{featureCount}</p>
                    <p className="text-xs text-slate-500">Features</p>
                  </div>
                </div>

                {eligible ? (
                  <p className="mt-4 line-clamp-2 text-xs leading-5 text-slate-600 dark:text-slate-300">
                    {eligible.justification}
                  </p>
                ) : null}

                <p className="mt-4 text-sm font-medium text-emerald-700 group-hover:underline">
                  Open Chart Room →
                </p>
              </Link>
            );
          })}
          </div>
        </div>
      </div>
    </div>
  );
}
