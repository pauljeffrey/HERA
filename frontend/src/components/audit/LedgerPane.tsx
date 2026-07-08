"use client";

import { useAuditContext } from "@/context/AuditContext";
import type { AuditPatient } from "@/lib/api";

function statusBadge(status: string) {
  const upper = status.toUpperCase();
  if (upper.includes("OVERRULED")) return "bg-amber-100 text-amber-900";
  if (upper.includes("ELIGIBLE")) return "bg-emerald-100 text-emerald-900";
  if (upper.includes("EXCLUDED") || upper.includes("FAILED")) return "bg-red-100 text-red-900";
  return "bg-slate-200 text-slate-800";
}

export default function LedgerPane({ patient }: { patient: AuditPatient | null }) {
  const { focusCriterion } = useAuditContext();

  if (!patient) {
    return <p className="text-sm text-slate-500">Eligibility ledger will appear here.</p>;
  }

  return (
    <div className="space-y-4">
      <div className={`rounded-xl px-3 py-2 text-sm font-semibold ${statusBadge(patient.overall_status)}`}>
        Final verdict: {patient.overall_status.replaceAll("_", " ")}
      </div>
      <p className="text-sm leading-6 text-slate-600 dark:text-slate-300">{patient.chain_of_thought_summary}</p>

      {patient.criteria_ledger.map((criterion) => (
        <button
          key={criterion.criterion_text}
          type="button"
          onMouseEnter={() => focusCriterion(patient, criterion)}
          className="panel-row w-full text-left"
        >
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="panel-label">
              {criterion.is_inclusion ? "Inclusion" : "Exclusion"}
            </span>
            <span className="text-xs font-medium">{criterion.verdict}</span>
          </div>
          <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{criterion.criterion_text}</p>
          {criterion.evidence_quote ? (
            <p className="mt-2 text-xs italic text-slate-500">&quot;{criterion.evidence_quote}&quot;</p>
          ) : null}
        </button>
      ))}
    </div>
  );
}
