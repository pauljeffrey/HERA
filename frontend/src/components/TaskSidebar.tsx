"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { fetchTaskStatus, saveTrackedTasks, type TrackedTask } from "@/lib/api";

type Props = {
  tasks: TrackedTask[];
  onTasksChange?: (tasks: TrackedTask[]) => void;
};

export default function TaskSidebar({ tasks, onTasksChange }: Props) {
  const [liveTasks, setLiveTasks] = useState(tasks);
  const tasksRef = useRef(tasks);

  useEffect(() => {
    tasksRef.current = tasks;
    setLiveTasks(tasks);
  }, [tasks]);

  useEffect(() => {
    const timer = setInterval(async () => {
      const snapshot = tasksRef.current;
      const active = snapshot.filter((task) => !["completed", "failed"].includes(task.status));
      if (!active.length) return;

      const updates = await Promise.all(
        active.map(async (task) => {
          try {
            const status = await fetchTaskStatus(task.task_id);
            const summary = status.result_summary || {};
            return {
              ...task,
              status: status.status,
              progress_percentage: status.progress_percentage,
              cohort_size: Number(summary.cohort_size ?? task.cohort_size ?? 0),
              top_diagnoses: (summary.top_diagnoses as string[]) || task.top_diagnoses || [],
              patient_ids_preview:
                (summary.patient_ids_preview as string[]) || task.patient_ids_preview || [],
            } satisfies TrackedTask;
          } catch {
            return task;
          }
        }),
      );

      const merged = snapshot.map(
        (task) => updates.find((item) => item.task_id === task.task_id) ?? task,
      );
      tasksRef.current = merged;
      setLiveTasks(merged);
      saveTrackedTasks(merged);
      onTasksChange?.(merged);
    }, 3000);

    return () => clearInterval(timer);
  }, [onTasksChange]);

  return (
    <aside className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <div>
        <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Recent searches</h2>
        <p className="mt-1 text-xs text-slate-500">Cohort matches appear here after you run a search.</p>
      </div>

      {liveTasks.length === 0 ? (
        <p className="text-sm text-slate-500">No searches yet.</p>
      ) : null}

      {liveTasks.map((task) => {
        const done = task.status === "completed";
        const failed = task.status === "failed";
        return (
          <div
            key={task.task_id}
            className="rounded-xl border border-slate-200/60 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900/70"
          >
            <div className="mb-2 flex items-center justify-between gap-2">
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                  done
                    ? "bg-emerald-100 text-emerald-800"
                    : failed
                      ? "bg-red-100 text-red-800"
                      : "bg-amber-100 text-amber-800"
                }`}
              >
                {done ? "Ready" : failed ? "Failed" : `In progress · ${task.progress_percentage}%`}
              </span>
            </div>

            {done ? (
              <>
                <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                  {task.cohort_size ?? 0} patients matched
                </p>
                {(task.top_diagnoses || []).length ? (
                  <p className="mt-1 text-xs text-slate-500">
                    Common themes: {(task.top_diagnoses || []).slice(0, 3).join(", ")}
                  </p>
                ) : null}
                <Link
                  href={`/audit/${task.task_id}`}
                  className="mt-3 inline-flex text-sm font-medium text-emerald-700 hover:text-emerald-900"
                >
                  Review results →
                </Link>
              </>
            ) : failed ? (
              <p className="text-xs text-red-600">This search could not be completed.</p>
            ) : (
              <>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
                  <div
                    className="h-full rounded-full bg-emerald-600 transition-all duration-300"
                    style={{ width: `${task.progress_percentage}%` }}
                  />
                </div>
                <Link
                  href={`/audit/${task.task_id}`}
                  className="mt-3 inline-flex text-sm font-medium text-emerald-700 hover:text-emerald-900"
                >
                  View progress →
                </Link>
              </>
            )}
          </div>
        );
      })}
    </aside>
  );
}
