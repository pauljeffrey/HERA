"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import CopilotPane from "@/components/audit/CopilotPane";
import LedgerPane from "@/components/audit/LedgerPane";
import MetricsPane from "@/components/audit/MetricsPane";
import TimelinePane from "@/components/audit/TimelinePane";
import { AuditProvider, useAuditContext } from "@/context/AuditContext";
import { fetchAuditDashboard, submitOverride, type AuditDashboard } from "@/lib/api";

function DashboardBody({ taskId }: { taskId: string }) {
  const { copilotOpen, setCopilotOpen, selectedPatientId, setSelectedPatientId } = useAuditContext();
  const [dashboard, setDashboard] = useState<AuditDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [overriding, setOverriding] = useState(false);

  const loadDashboard = useCallback(async () => {
    try {
      const data = await fetchAuditDashboard(taskId);
      setDashboard(data);
      setError(null);
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
      return null;
    }
  }, [taskId]);

  useEffect(() => {
    loadDashboard().then((data) => {
      if (data?.patients[0] && !selectedPatientId) {
        setSelectedPatientId(data.patients[0].patient_id);
      }
    });
  }, [loadDashboard, selectedPatientId, setSelectedPatientId]);

  useEffect(() => {
    if (!dashboard || ["completed", "failed"].includes(dashboard.status)) return;
    const timer = setInterval(() => {
      loadDashboard();
    }, 5000);
    return () => clearInterval(timer);
  }, [dashboard?.status, loadDashboard]);

  const patient = useMemo(
    () => dashboard?.patients.find((item) => item.patient_id === selectedPatientId) ?? dashboard?.patients[0] ?? null,
    [dashboard, selectedPatientId],
  );

  async function handleOverride() {
    if (!patient || !dashboard || overriding) return;
    const reason = window.prompt("Enter override rationale (min 10 chars):");
    if (!reason || reason.trim().length < 10) return;

    setOverriding(true);
    try {
      await submitOverride(taskId, {
        patient_id: patient.patient_id,
        trial_id: dashboard.trial_id,
        encounter_id: "AUDIT_DASHBOARD",
        override_status: "OVERRULED",
        override_reason_text: reason,
      });
      await loadDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Override failed");
    } finally {
      setOverriding(false);
    }
  }

  const inProgress = dashboard && !["completed", "failed"].includes(dashboard.status);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <header className="border-b border-slate-200/60 bg-white/80 px-6 py-4 backdrop-blur-md dark:border-slate-800">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-3">
          <div>
            <Link href="/" className="text-xs text-emerald-700 hover:underline">
              ← Command Center
            </Link>
            <h1 className="page-title">
              Audit Dashboard · {dashboard?.trial_id ?? taskId}
            </h1>
            <p className="text-sm text-slate-500">
              {inProgress
                ? `Matching in progress (${dashboard.progress_percentage}%)…`
                : `Cohort: ${dashboard?.cohort_size ?? 0} patients`}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handleOverride}
              disabled={!patient || overriding || Boolean(inProgress)}
              className="btn-secondary hover:border-amber-500"
            >
              {overriding ? "Saving…" : "Overrule Verdict"}
            </button>
            <button type="button" onClick={() => setCopilotOpen(!copilotOpen)} className="btn-primary">
              {copilotOpen ? "Hide Copilot" : "Toggle Copilot"}
            </button>
          </div>
        </div>
      </header>

      {error ? <p className="px-6 py-4 text-sm text-red-600">{error}</p> : null}

      {inProgress ? (
        <p className="px-6 py-8 text-sm text-slate-500">
          Results are still being prepared. This page will update automatically.
        </p>
      ) : null}

      <div className="mx-auto max-w-[1600px] p-4">
        <div className="mb-4 flex flex-wrap gap-2">
          {(dashboard?.patients ?? []).map((item) => (
            <button
              key={item.patient_id}
              type="button"
              onClick={() => setSelectedPatientId(item.patient_id)}
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                selectedPatientId === item.patient_id
                  ? "bg-emerald-700 text-white"
                  : "bg-white text-slate-700 ring-1 ring-slate-200"
              }`}
            >
              {item.patient_id}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-12 gap-4 transition-all duration-300 ease-in-out">
          <section
            className={`panel ${copilotOpen ? "col-span-12 lg:col-span-4" : "col-span-12 lg:col-span-5"}`}
          >
            <h2 className="panel-heading">Source EHR Timeline</h2>
            <TimelinePane patient={patient} />
          </section>

          <section
            className={`panel ${copilotOpen ? "col-span-12 lg:col-span-2" : "col-span-12 lg:col-span-3"}`}
          >
            <h2 className="panel-heading">Metric Matrix</h2>
            <MetricsPane patient={patient} />
          </section>

          <section
            className={`panel ${copilotOpen ? "col-span-12 lg:col-span-3" : "col-span-12 lg:col-span-4"}`}
          >
            <h2 className="panel-heading">Eligibility Ledger</h2>
            <LedgerPane patient={patient} />
          </section>

          {copilotOpen ? (
            <section className="panel col-span-12 transition-all duration-300 ease-in-out lg:col-span-3">
              <CopilotPane taskId={taskId} onPatientUpdate={loadDashboard} />
            </section>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export default function AuditDashboardPage({ taskId }: { taskId: string }) {
  return (
    <AuditProvider>
      <DashboardBody taskId={taskId} />
    </AuditProvider>
  );
}
