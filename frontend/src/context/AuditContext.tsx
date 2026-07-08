"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

import type { AuditPatient, CriterionAudit, ExtractedFeature } from "@/lib/api";

type HighlightTarget = {
  patientId: string;
  quote?: string;
  encounterIndex?: number;
  spanStart?: number;
  spanEnd?: number;
};

type AuditContextValue = {
  selectedPatientId: string | null;
  setSelectedPatientId: (id: string | null) => void;
  copilotOpen: boolean;
  setCopilotOpen: (open: boolean) => void;
  highlight: HighlightTarget | null;
  setHighlight: (target: HighlightTarget | null) => void;
  focusCriterion: (patient: AuditPatient, criterion: CriterionAudit) => void;
  focusFeature: (patient: AuditPatient, feature: ExtractedFeature) => void;
};

const AuditContext = createContext<AuditContextValue | null>(null);

export function AuditProvider({ children }: { children: ReactNode }) {
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);
  const [copilotOpen, setCopilotOpen] = useState(true);
  const [highlight, setHighlight] = useState<HighlightTarget | null>(null);

  const value = useMemo<AuditContextValue>(
    () => ({
      selectedPatientId,
      setSelectedPatientId,
      copilotOpen,
      setCopilotOpen,
      highlight,
      setHighlight,
      focusCriterion: (patient, criterion) => {
        setSelectedPatientId(patient.patient_id);
        setHighlight({
          patientId: patient.patient_id,
          quote: criterion.evidence_quote || undefined,
          encounterIndex: undefined,
        });
      },
      focusFeature: (patient, feature) => {
        setSelectedPatientId(patient.patient_id);
        setHighlight({
          patientId: patient.patient_id,
          encounterIndex: feature.encounter_index,
          spanStart: feature.source_span_start,
          spanEnd: feature.source_span_end,
        });
      },
    }),
    [selectedPatientId, copilotOpen, highlight],
  );

  return <AuditContext.Provider value={value}>{children}</AuditContext.Provider>;
}

export function useAuditContext() {
  const ctx = useContext(AuditContext);
  if (!ctx) throw new Error("useAuditContext must be used within AuditProvider");
  return ctx;
}
