"use client";

import type { PatientBiodata } from "@/lib/api";

export default function PatientBiodataCard({
  biodata,
  loading,
}: {
  biodata: PatientBiodata | null;
  loading?: boolean;
}) {
  if (loading) {
    return (
      <div className="rounded-xl border border-slate-200/60 bg-white/70 px-4 py-3 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900/50">
        Loading patient biodata…
      </div>
    );
  }

  if (!biodata) {
    return (
      <div className="rounded-xl border border-slate-200/60 bg-white/70 px-4 py-3 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900/50">
        Biodata unavailable for this patient.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-emerald-200/70 bg-emerald-50/50 px-4 py-3 dark:border-emerald-900/40 dark:bg-emerald-950/20">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-base font-semibold text-slate-900 dark:text-slate-100">{biodata.name}</p>
          <p className="font-mono text-xs text-emerald-700">{biodata.patient_id}</p>
        </div>
        <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-emerald-800 dark:bg-slate-900">
          {biodata.encounter_count} encounter{biodata.encounter_count === 1 ? "" : "s"}
        </span>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">Age</dt>
          <dd className="font-medium text-slate-800 dark:text-slate-100">{biodata.age}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">Sex</dt>
          <dd className="font-medium text-slate-800 dark:text-slate-100">{biodata.sex}</dd>
        </div>
        {biodata.specialty_label ? (
          <div className="col-span-2">
            <dt className="text-xs uppercase tracking-wide text-slate-500">Specialty</dt>
            <dd className="font-medium text-slate-800 dark:text-slate-100">{biodata.specialty_label}</dd>
          </div>
        ) : null}
      </dl>
    </div>
  );
}
