"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import CopilotPane from "@/components/audit/CopilotPane";
import LedgerPane from "@/components/audit/LedgerPane";
import PatientBiodataCard from "@/components/audit/PatientBiodataCard";
import TimelinePane from "@/components/audit/TimelinePane";
import TaskProgressBar from "@/components/TaskProgressBar";
import { AuditProvider, useAuditContext } from "@/context/AuditContext";
import { fetchAuditDashboard, submitOverride, type AuditDashboard } from "@/lib/api";
import { normalizeTaskId } from "@/lib/task_id";

function ScrollPanel({
  title,
  subtitle,
  open,
  onToggle,
  children,
  className = "",
}: {
  title: string;
  subtitle?: string;
  open?: boolean;
  onToggle?: () => void;
  children: React.ReactNode;
  className?: string;
}) {
  const collapsible = onToggle != null;

  return (
    <section className={`panel flex h-[68vh] min-h-[560px] flex-col ${className}`}>
      {collapsible ? (
        <button
          type="button"
          onClick={onToggle}
          className="mb-3 flex w-full shrink-0 items-center justify-between gap-2 text-left"
        >
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>
            {subtitle ? <p className="mt-0.5 text-xs text-slate-400">{subtitle}</p> : null}
          </div>
          <span className="shrink-0 text-xs text-emerald-700">{open ? "Hide" : "Show"}</span>
        </button>
      ) : (
        <h2 className="panel-heading shrink-0">{title}</h2>
      )}
      {collapsible && !open ? null : <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>}
    </section>
  );
}

function DashboardBody({ taskId: rawTaskId }: { taskId: string }) {
  const taskId = useMemo(() => {
    try {
      return normalizeTaskId(rawTaskId);
    } catch {
      return rawTaskId;
    }
  }, [rawTaskId]);
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
    <div className="min-h-[calc(100vh-49px)] bg-slate-50 dark:bg-slate-950">
      <header className="shrink-0 border-b border-slate-200/60 bg-white/80 px-6 py-3 backdrop-blur-md dark:border-slate-800">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-3">
          <div>
            <Link href="/" className="text-xs text-emerald-700 hover:underline">
              ← Command Center
            </Link>
            <h1 className="page-title">Audit Dashboard · {dashboard?.trial_id ?? taskId}</h1>
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

      {error ? <p className="shrink-0 px-6 py-2 text-sm text-red-600">{error}</p> : null}

      {inProgress ? (
        <div className="shrink-0 border-b border-amber-200/60 bg-amber-50/80 px-6 py-3 dark:border-amber-900/40 dark:bg-amber-950/30">
          <div className="mx-auto max-w-[1600px]">
            <TaskProgressBar progress={dashboard.progress_percentage} label="Matching in progress" />
            <p className="mt-2 text-xs text-slate-600 dark:text-slate-400">
              Results are still being prepared. This page updates automatically every few seconds.
            </p>
          </div>
        </div>
      ) : null}

      <div className="mx-auto w-full max-w-[1600px] p-4 pb-8">
        <div className="mb-4 space-y-3">
          <div className="flex flex-wrap gap-2">
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
          {selectedPatientId ? (
            <PatientBiodataCard biodata={patient?.biodata ?? null} />
          ) : null}
        </div>

        <div className={`grid items-stretch gap-4 ${copilotOpen ? "lg:grid-cols-12" : "lg:grid-cols-2"}`}>
          <ScrollPanel
            title="Source EHR Timeline"
            className={copilotOpen ? "col-span-12 lg:col-span-5" : "col-span-12"}
          >
            <TimelinePane patient={patient} />
          </ScrollPanel>

          <ScrollPanel
            title="Eligibility Ledger"
            className={copilotOpen ? "col-span-12 lg:col-span-4" : "col-span-12"}
          >
            <LedgerPane patient={patient} />
          </ScrollPanel>

          {copilotOpen ? (
            <section className="panel col-span-12 flex h-[68vh] min-h-[560px] flex-col lg:col-span-3">
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
