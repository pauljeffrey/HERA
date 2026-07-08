"use client";

import { useEffect, useRef } from "react";

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
  const refs = useRef<Record<number, HTMLDivElement | null>>({});

  useEffect(() => {
    if (!highlight?.encounterIndex && highlight?.encounterIndex !== 0) return;
    refs.current[highlight.encounterIndex]?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlight]);

  if (!patient) {
    return <p className="text-sm text-slate-500">Select a patient to inspect source EHR notes.</p>;
  }

  return (
    <div className="space-y-4">
      {patient.encounters.map((encounter) => {
        const active =
          highlight?.patientId === patient.patient_id &&
          (highlight.encounterIndex === encounter.encounter_index ||
            Boolean(highlight.quote && encounter.soap_note.includes(highlight.quote)));

        return (
          <div
            key={encounter.encounter_id}
            ref={(node) => {
              refs.current[encounter.encounter_index] = node;
            }}
            className={`rounded-xl border p-4 transition-all duration-300 ${
              active
                ? "border-amber-500 bg-amber-100/70 dark:bg-amber-900/40"
                : "border-slate-200/60 bg-white/70 dark:border-slate-800 dark:bg-slate-900/50"
            }`}
          >
            <p className="panel-label mb-2">
              {encounter.encounter_type} · ENC-{encounter.encounter_index + 1}
            </p>
            <pre className="whitespace-pre-wrap font-sans text-sm leading-6 text-slate-800 dark:text-slate-100">
              {highlight?.patientId === patient.patient_id
                ? highlightText(
                    encounter.soap_note,
                    highlight.spanStart,
                    highlight.spanEnd,
                    highlight.quote,
                  )
                : encounter.soap_note}
            </pre>
          </div>
        );
      })}
    </div>
  );
}
