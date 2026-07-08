"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { fetchPatient, type PatientSnapshot } from "@/lib/api";

export default function PatientChartRoom({ patientId }: { patientId: string }) {
  const [snapshot, setSnapshot] = useState<PatientSnapshot | null>(null);
  const [activeEncounter, setActiveEncounter] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchPatient(patientId)
      .then(setSnapshot)
      .catch((err: Error) => setError(err.message));
  }, [patientId]);

  const audit = useMemo(
    () => snapshot?.audit_payload.selected_patients.find((p) => p.patient_id === patientId),
    [snapshot, patientId],
  );

  const encounter = snapshot?.encounters[activeEncounter];

  if (error) {
    return <p className="p-6 text-sm text-red-600">{error}</p>;
  }

  if (!snapshot) {
    return <p className="p-6 text-sm text-slate-500">Loading chart for {patientId}…</p>;
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <header className="border-b border-slate-200/60 bg-white/80 px-6 py-6 backdrop-blur-md dark:border-slate-800">
        <div className="mx-auto flex max-w-7xl flex-wrap items-end justify-between gap-4">
          <div>
            <Link href="/patients" className="text-xs text-emerald-700 hover:underline">
              ← Patient Atlas
            </Link>
            <h1 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">{patientId}</h1>
            <p className="text-sm text-slate-500">
              {snapshot.trial_id} · {snapshot.encounters.length} encounters · {snapshot.extracted_features.length}{" "}
              extracted features
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              href={`/patients/${patientId}/audit-trail`}
              className="rounded-xl border border-slate-300 px-4 py-2 text-sm hover:border-emerald-500"
            >
              Audit Trail
            </Link>
            <Link
              href={`/?seed=${encodeURIComponent(`Screen patients where: ${audit?.criteria_ledger[0]?.criterion_text ?? "LVEF below 40%"}`)}`}
              className="rounded-xl bg-emerald-700 px-4 py-2 text-sm font-medium text-white"
            >
              Match This Patient
            </Link>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-7xl gap-4 p-6 lg:grid-cols-12">
        <aside className="space-y-2 lg:col-span-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Timeline</p>
          {snapshot.encounters.map((enc, index) => (
            <button
              key={enc.encounter_id}
              type="button"
              onClick={() => setActiveEncounter(index)}
              className={`w-full rounded-xl border px-3 py-2 text-left text-sm transition ${
                activeEncounter === index
                  ? "border-emerald-500 bg-emerald-50 text-emerald-900"
                  : "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
              }`}
            >
              <span className="font-medium">{enc.encounter_type}</span>
              <span className="mt-0.5 block text-xs text-slate-500">Day {enc.days_since_baseline ?? index}</span>
            </button>
          ))}
        </aside>

        <section className="rounded-2xl border border-slate-200/60 bg-white/80 p-4 lg:col-span-5 dark:border-slate-800 dark:bg-slate-900/70">
          <h2 className="panel-heading">SOAP Note</h2>
          {encounter ? (
            <pre className="max-h-[520px] overflow-y-auto whitespace-pre-wrap font-sans text-sm leading-6 text-slate-800 dark:text-slate-100">
              {encounter.soap_note}
            </pre>
          ) : null}
        </section>

        <section className="space-y-4 lg:col-span-4">
          <div className="rounded-2xl border border-slate-200/60 bg-white/80 p-4 dark:border-slate-800 dark:bg-slate-900/70">
            <h2 className="panel-heading">Feature Heatmap</h2>
            <div className="space-y-2">
              {snapshot.extracted_features.slice(0, 12).map((feature) => (
                <div
                  key={`${feature.field_name}-${feature.encounter_index}-${feature.source_span_start}`}
                  className="rounded-lg border border-slate-200 p-2 dark:border-slate-700"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-medium text-slate-700 dark:text-slate-200">{feature.field_name}</span>
                    <span className="text-xs text-emerald-700">{Math.round(feature.confidence_score * 100)}%</span>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">{feature.normalized_value}</p>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                    <div
                      className="h-full rounded-full bg-emerald-600"
                      style={{ width: `${feature.confidence_score * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {audit ? (
            <div className="rounded-2xl border border-slate-200/60 bg-white/80 p-4 dark:border-slate-800 dark:bg-slate-900/70">
              <h2 className="panel-heading">Mock Eligibility</h2>
              <p className="text-sm leading-6 text-slate-700 dark:text-slate-200">{audit.justification}</p>
              <ul className="mt-3 space-y-2">
                {audit.criteria_ledger.slice(0, 4).map((item) => (
                  <li key={item.criterion_text} className="rounded-lg bg-slate-50 p-2 text-xs dark:bg-slate-800/50">
                    <span className="font-medium">{item.verdict}</span> — {item.criterion_text.slice(0, 80)}…
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
