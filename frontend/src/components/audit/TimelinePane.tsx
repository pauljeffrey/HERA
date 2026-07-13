"use client";

import { useEffect, useState } from "react";

import { useAuditContext } from "@/context/AuditContext";
import type { AuditPatient } from "@/lib/api";

function highlightText(text: string, start?: number, end?: number, quote?: string) {
  if (quote && text.includes(quote)) {
    const idx = text.indexOf(quote);
    return (
      <>
        {text.slice(0, idx)}
        <mark className="rounded bg-amber-100 px-1 dark:bg-amber-900/40">{quote}</mark>
        {text.slice(idx + quote.length)}
      </>
    );
  }
  if (start != null && end != null && end <= text.length) {
    return (
      <>
        {text.slice(0, start)}
        <mark className="rounded bg-amber-100 px-1 dark:bg-amber-900/40">{text.slice(start, end)}</mark>
        {text.slice(end)}
      </>
    );
  }
  return text;
}

export default function TimelinePane({ patient }: { patient: AuditPatient | null }) {
  const { highlight } = useAuditContext();
  const [activeEncounter, setActiveEncounter] = useState(0);

  useEffect(() => {
    if (!patient) return;
    if (highlight?.patientId !== patient.patient_id) return;

    if (highlight.encounterIndex != null) {
      setActiveEncounter(highlight.encounterIndex);
      return;
    }

    if (highlight.quote) {
      const match = patient.encounters.findIndex((enc) => enc.soap_note.includes(highlight.quote!));
      if (match >= 0) setActiveEncounter(match);
    }
  }, [highlight, patient]);

  useEffect(() => {
    setActiveEncounter(0);
  }, [patient?.patient_id]);

  if (!patient) {
    return <p className="text-sm text-slate-500">Select a patient to inspect source EHR notes.</p>;
  }

  const encounter = patient.encounters[activeEncounter];
  const activeHighlight =
    highlight?.patientId === patient.patient_id &&
    (highlight.encounterIndex === encounter?.encounter_index ||
      Boolean(highlight.quote && encounter?.soap_note.includes(highlight.quote)));

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="shrink-0 space-y-1.5">
        {patient.encounters.map((enc, index) => {
          const selected = activeEncounter === index;
          return (
            <button
              key={enc.encounter_id}
              type="button"
              onClick={() => setActiveEncounter(index)}
              className={`w-full rounded-xl border px-3 py-2 text-left text-sm transition ${
                selected
                  ? "border-emerald-500 bg-emerald-50 text-emerald-900 dark:bg-emerald-950/40"
                  : "border-slate-200 bg-white hover:border-emerald-300 dark:border-slate-800 dark:bg-slate-900"
              }`}
            >
              <span className="font-medium">{enc.encounter_type}</span>
              <span className="mt-0.5 block text-xs text-slate-500">
                ENC-{enc.encounter_index + 1}
                {enc.days_since_baseline != null ? ` · Day ${enc.days_since_baseline}` : ""}
              </span>
            </button>
          );
        })}
      </div>

      {encounter ? (
        <div
          className={`min-h-0 flex-1 overflow-y-auto rounded-xl border p-4 transition-all duration-300 ${
            activeHighlight
              ? "border-amber-500 bg-amber-100/70 dark:bg-amber-900/40"
              : "border-slate-200/60 bg-white/70 dark:border-slate-800 dark:bg-slate-900/50"
          }`}
        >
          <p className="panel-label mb-2">
            {encounter.encounter_type} · ENC-{encounter.encounter_index + 1}
          </p>
          <pre className="whitespace-pre-wrap font-sans text-sm leading-6 text-slate-800 dark:text-slate-100">
            {activeHighlight
              ? highlightText(
                  encounter.soap_note,
                  highlight?.spanStart,
                  highlight?.spanEnd,
                  highlight?.quote,
                )
              : encounter.soap_note}
          </pre>
        </div>
      ) : null}
    </div>
  );

}
