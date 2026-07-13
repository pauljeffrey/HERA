"use client";

import Link from "next/link";
import { useState } from "react";

import { fetchPatientRecord, type PatientClinicalRecord } from "@/lib/api";

function normalizePatientId(raw: string): string | null {
  const trimmed = raw.trim().toUpperCase();
  const match = trimmed.match(/^PT-(\d+)$/);
  if (!match) return null;
  return `PT-${match[1].padStart(6, "0")}`;
}

export default function PatientLookupSidebar() {
  const [open, setOpen] = useState(true);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [record, setRecord] = useState<PatientClinicalRecord | null>(null);
  const [expandedEncounter, setExpandedEncounter] = useState<number | null>(null);

  async function lookup(event: React.FormEvent) {
    event.preventDefault();
    const patientId = normalizePatientId(query);
    if (!patientId) {
      setError("Enter a patient ID like PT-000541.");
      return;
    }

    setLoading(true);
    setError(null);
    setRecord(null);
    setExpandedEncounter(null);
    try {
      const data = await fetchPatientRecord(patientId);
      setRecord(data);
      if (data.encounters.length) {
        setExpandedEncounter(data.encounters[0].encounter_index);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lookup failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <aside className="shrink-0 border-b border-slate-200/70 bg-white/90 dark:border-slate-800 dark:bg-slate-950/90 lg:max-h-[calc(100vh-180px)] lg:w-96 lg:overflow-y-auto lg:border-b-0 lg:border-r">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between px-4 py-3 text-left lg:hidden"
      >
        <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">Patient lookup</span>
        <span className="text-xs text-slate-500">{open ? "Hide" : "Show"}</span>
      </button>

      <div className={`${open ? "block" : "hidden"} space-y-4 p-4 lg:block`}>
        <div>
          <h2 className="hidden text-sm font-semibold text-slate-900 dark:text-slate-100 lg:block">
            Patient lookup
          </h2>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            Confirm chart details while chatting in the Command Center. Enter a patient ID (e.g.{" "}
            <code className="text-emerald-700">PT-000541</code>).
          </p>
        </div>

        <form onSubmit={lookup} className="space-y-2">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value.toUpperCase())}
            placeholder="PT-000541"
            className="w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm outline-none ring-emerald-600 focus:ring-2 dark:border-slate-700 dark:bg-slate-900"
          />
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="w-full rounded-lg bg-emerald-700 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-40"
          >
            {loading ? "Loading…" : "Look up patient"}
          </button>
        </form>

        {error ? <p className="text-xs text-red-600">{error}</p> : null}

        {record ? (
          <div className="space-y-3 rounded-xl border border-slate-200/60 bg-slate-50/80 p-3 dark:border-slate-800 dark:bg-slate-900/50">
            <div>
              <p className="font-semibold text-slate-900 dark:text-slate-100">{record.biodata.name}</p>
              <p className="font-mono text-xs text-emerald-700">{record.biodata.patient_id}</p>
              <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                {record.biodata.age}y · {record.biodata.sex}
                {record.biodata.specialty_label ? ` · ${record.biodata.specialty_label}` : ""}
              </p>
            </div>

            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Encounters ({record.encounters.length})
              </p>
              {record.encounters.map((enc) => {
                const expanded = expandedEncounter === enc.encounter_index;
                return (
                  <div
                    key={enc.encounter_id}
                    className="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-950/60"
                  >
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedEncounter(expanded ? null : enc.encounter_index)
                      }
                      className="flex w-full items-start justify-between gap-2 px-3 py-2 text-left"
                    >
                      <span className="text-xs font-medium text-slate-800 dark:text-slate-100">
                        {enc.encounter_type}
                        <span className="mt-0.5 block font-normal text-slate-500">
                          {enc.encounter_id}
                        </span>
                      </span>
                      <span className="shrink-0 text-[10px] text-slate-400">{expanded ? "−" : "+"}</span>
                    </button>
                    {expanded ? (
                      <div className="space-y-3 border-t border-slate-200 px-3 py-2 text-xs dark:border-slate-700">
                        {enc.soap_excerpt ? (
                          <p className="whitespace-pre-wrap leading-5 text-slate-600 dark:text-slate-300">
                            {enc.soap_excerpt}
                          </p>
                        ) : null}
                        {enc.labs.length ? (
                          <div>
                            <p className="font-semibold text-slate-700 dark:text-slate-200">Labs</p>
                            <ul className="mt-1 space-y-1">
                              {enc.labs.map((lab) => (
                                <li key={`${lab.test_name}-${lab.test_value}`}>
                                  {lab.test_name}: {lab.test_value}
                                  {lab.panel ? ` (${lab.panel})` : ""}
                                </li>
                              ))}
                            </ul>
                          </div>
                        ) : (
                          <p className="text-slate-400">No structured labs for this encounter.</p>
                        )}
                        {enc.investigations.length ? (
                          <div>
                            <p className="font-semibold text-slate-700 dark:text-slate-200">Investigations</p>
                            <ul className="mt-1 list-disc pl-4">
                              {enc.investigations.map((item) => (
                                <li key={item}>{item}</li>
                              ))}
                            </ul>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>

            <Link
              href={`/patients/${record.biodata.patient_id}`}
              className="inline-flex text-xs font-medium text-emerald-700 hover:underline"
            >
              Open full chart room →
            </Link>
          </div>
        ) : null}
      </div>
    </aside>
  );
}
