"use client";

import { useAuditContext } from "@/context/AuditContext";
import type { AuditPatient } from "@/lib/api";

function sourceLabel(tier: string) {
  if (tier.includes("Agentic")) {
    return <span className="rounded bg-purple-100 px-2 py-0.5 text-[10px] font-medium text-purple-800">Clinical review</span>;
  }
  if (tier.includes("Vector") || tier.includes("Regex")) {
    return <span className="rounded bg-blue-100 px-2 py-0.5 text-[10px] font-medium text-blue-800">Validated</span>;
  }
  return <span className="rounded bg-slate-200 px-2 py-0.5 text-[10px] font-medium text-slate-700">Chart data</span>;
}

export default function MetricsPane({ patient }: { patient: AuditPatient | null }) {
  const { focusFeature } = useAuditContext();

  if (!patient) {
    return <p className="text-sm text-slate-500">Extracted metrics will appear here.</p>;
  }

  return (
    <div className="space-y-3">
      {patient.extracted_features.map((feature, index) => (
        <button
          key={`${feature.field_name}-${index}`}
          type="button"
          onMouseEnter={() => focusFeature(patient, feature)}
          className="panel-row w-full text-left transition hover:border-emerald-400"
        >
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="font-medium text-slate-900 dark:text-slate-100">{feature.field_name}</span>
            {sourceLabel(feature.pipeline_tier)}
          </div>
          <p className="text-sm text-slate-700 dark:text-slate-200">{feature.normalized_value}</p>
          <p className="mt-1 text-xs text-slate-500">Encounter {feature.encounter_index + 1}</p>
        </button>
      ))}
    </div>
  );
}
