"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { fetchAuditLogs, type AuditLogEntry } from "@/lib/api";

export default function AuditTrailView({ patientId }: { patientId: string }) {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAuditLogs(patientId)
      .then(setLogs)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [patientId]);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <header className="border-b border-slate-200/60 bg-white/80 px-6 py-6 backdrop-blur-md dark:border-slate-800">
        <div className="mx-auto max-w-3xl">
          <Link href={`/patients/${patientId}`} className="text-xs text-emerald-700 hover:underline">
            ← Chart Room
          </Link>
          <h1 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">Audit Trail</h1>
          <p className="text-sm text-slate-500">
            Clinician overrides and eligibility reviews for {patientId}
          </p>
        </div>
      </header>

      <div className="mx-auto max-w-3xl p-6">
        {loading ? <p className="text-sm text-slate-500">Loading audit history…</p> : null}
        {error ? <p className="text-sm text-red-600">{error}</p> : null}

        {!loading && logs.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 p-8 text-center dark:border-slate-700">
            <p className="text-sm text-slate-500">No audit logs yet for this patient.</p>
            <p className="mt-2 text-xs text-slate-400">
              Overrides and eligibility decisions from the review dashboard appear here.
            </p>
          </div>
        ) : null}

        <ol className="relative space-y-6 border-l-2 border-emerald-200 pl-6 dark:border-emerald-900">
          {logs.map((log) => {
            const isOverride = Boolean(log.clinician_override_status);
            return (
              <li key={log.log_id} className="relative">
                <span
                  className={`absolute -left-[1.6rem] top-1 flex h-4 w-4 items-center justify-center rounded-full ring-4 ring-slate-50 dark:ring-slate-950 ${
                    isOverride ? "bg-amber-500" : "bg-emerald-600"
                  }`}
                />
                <div className="rounded-2xl border border-slate-200/60 bg-white/80 p-4 dark:border-slate-800 dark:bg-slate-900/70">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      {log.encounter_id}
                    </span>
                    <time className="text-xs text-slate-400">{log.timestamp || "—"}</time>
                  </div>
                  <p className="mt-2 text-sm font-medium text-slate-900 dark:text-slate-100">
                    {isOverride ? log.clinician_override_status : "Eligibility review recorded"}
                  </p>
                  {log.override_reason_text ? (
                    <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                      {log.override_reason_text}
                    </p>
                  ) : null}
                  <p className="mt-2 text-xs text-slate-400">Trial: {log.trial_id}</p>
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
