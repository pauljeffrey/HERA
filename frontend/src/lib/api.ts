export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8010/api/v1";
export const API_ORIGIN = API_BASE.replace(/\/api\/v1\/?$/, "");

export type CriteriaPrompt = { text: string; patient_count: number };

export type CriteriaPromptsResponse = {
  source: string;
  count: number;
  prompts: CriteriaPrompt[];
};

export type ChatResponse = {
  reply: string;
  conversation_id: string;
  suggested_patient_id?: string | null;
  search_payload?: unknown;
};

export type TaskStatus = {
  task_id: string;
  user_id: string;
  trial_id: string;
  status: string;
  progress_percentage: number;
  result_summary: Record<string, unknown>;
  created_at?: string;
};

export type ExtractedFeature = {
  field_name: string;
  raw_text: string;
  normalized_value: string;
  pipeline_tier: string;
  confidence_score: number;
  encounter_index: number;
  source_span_start: number;
  source_span_end: number;
};

export type EncounterNote = {
  encounter_id: string;
  encounter_index: number;
  encounter_type: string;
  soap_note: string;
  days_since_baseline?: number;
};

export type CriterionAudit = {
  criterion_text: string;
  is_inclusion: boolean;
  verdict: string;
  evidence_quote?: string | null;
  encounter_date_cited?: string | null;
  reasoning?: string;
};

export type AuditPatient = {
  patient_id: string;
  trial_id: string;
  overall_status: string;
  chain_of_thought_summary: string;
  criteria_ledger: CriterionAudit[];
  encounters: EncounterNote[];
  extracted_features: ExtractedFeature[];
  override_status?: string | null;
  biodata?: PatientBiodata | null;
};

export type AuditDashboard = {
  task_id: string;
  trial_id: string;
  status: string;
  progress_percentage: number;
  cohort_size: number;
  patient_ids_preview: string[];
  top_diagnoses: string[];
  search_metrics: Record<string, number>;
  patients: AuditPatient[];
};

export type CopilotResponse = {
  reply: string;
  scope: string;
  suggested_chips: string[];
  override_applied: boolean;
  updated_patient_id?: string | null;
  updated_overall_status?: string | null;
};

export type TrackedTask = {
  task_id: string;
  trial_id: string;
  status: string;
  progress_percentage: number;
  response: string;
  cohort_size?: number;
  top_diagnoses?: string[];
  patient_ids_preview?: string[];
};

export type RandomPatientResponse = {
  total_patients: number;
  patient: PatientBiodata | null;
};

export type PatientBiodata = {
  patient_id: string;
  name: string;
  age: number;
  sex: string;
  specialty_label?: string | null;
  encounter_count: number;
};

export type RandomCriterionResponse = {
  source: string;
  count: number;
  criterion: CriteriaPrompt | null;
};

export type IndividualCriterionEvaluation = {
  criterion_text: string;
  is_inclusion: boolean;
  verdict: string;
  evidence_quote?: string | null;
  confidence_score: number;
};

export type EligiblePatient = {
  patient_id: string;
  trial_id: string;
  overall_eligible: boolean;
  justification: string;
  criteria_ledger: IndividualCriterionEvaluation[];
};

export type PatientAuditPayload = {
  selected_patients: EligiblePatient[];
  execution_latency_ms: number;
  token_cost_usd: number;
  search_space_raw: number;
  search_space_after_fts: number;
  search_space_after_vs: number;
  search_space_final: number;
};

export type PatientSnapshot = {
  patient_id: string;
  trial_id: string;
  snapshot_id: string;
  encounters: EncounterNote[];
  extracted_features: ExtractedFeature[];
  audit_payload: PatientAuditPayload;
};

export type AuditLogEntry = {
  log_id: string;
  patient_id: string;
  encounter_id: string;
  trial_id: string;
  clinician_override_status?: string | null;
  override_reason_text?: string | null;
  timestamp: string;
};

export const CRITERIA_SEED_KEY = "hera_criteria_seed";

import { normalizeTaskId } from "./task_id";

async function parseError(res: Response, fallback: string) {
  const text = await res.text();
  try {
    const body = JSON.parse(text) as { detail?: string };
    if (typeof body.detail === "string") throw new Error(body.detail);
  } catch (err) {
    if (err instanceof Error && err.message !== text) throw err;
  }
  throw new Error(text.length < 200 ? text : `${fallback} (${res.status})`);
}

export async function fetchCriteriaPrompts(limit = 20): Promise<CriteriaPromptsResponse> {
  const res = await fetch(`${API_BASE}/criteria/prompts?limit=${limit}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load criteria prompts (${res.status})`);
  return res.json();
}

export async function sendChatMessage(
  message: string,
  conversationId?: string | null,
  patientId?: string | null,
) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_id: conversationId ?? undefined,
      patient_id: patientId ?? undefined,
    }),
  });
  if (!res.ok) await parseError(res, "Chat request failed");
  return res.json() as Promise<ChatResponse>;
}

export type StreamEventHandlers = {
  onStatus?: (text: string) => void;
  onDelta?: (text: string) => void;
  onDone?: (payload: ChatResponse) => void;
  onError?: (message: string) => void;
};

async function consumeSseStream(
  res: Response,
  handlers: StreamEventHandlers,
): Promise<ChatResponse | null> {
  const reader = res.body?.getReader();
  if (!reader) throw new Error("Streaming is not supported in this browser.");

  const decoder = new TextDecoder();
  let buffer = "";
  let donePayload: ChatResponse | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      const line = part
        .split("\n")
        .find((row) => row.startsWith("data: "));
      if (!line) continue;
      const payload = JSON.parse(line.slice(6)) as {
        type?: string;
        content?: string;
        reply?: string;
        conversation_id?: string;
        suggested_patient_id?: string | null;
        search_payload?: unknown;
      };

      if (payload.type === "status" && payload.content) {
        handlers.onStatus?.(payload.content);
      } else if (payload.type === "delta" && payload.content) {
        handlers.onDelta?.(payload.content);
      } else if (payload.type === "error" && payload.content) {
        handlers.onError?.(payload.content);
        throw new Error(payload.content);
      } else if (payload.type === "done" && payload.reply && payload.conversation_id) {
        donePayload = {
          reply: payload.reply,
          conversation_id: payload.conversation_id,
          suggested_patient_id: payload.suggested_patient_id,
          search_payload: payload.search_payload,
        };
        handlers.onDone?.(donePayload);
      }
    }
  }

  return donePayload;
}

export async function streamChatMessage(
  message: string,
  handlers: StreamEventHandlers,
  conversationId?: string | null,
  patientId?: string | null,
) {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_id: conversationId ?? undefined,
      patient_id: patientId ?? undefined,
    }),
  });
  if (!res.ok) await parseError(res, "Chat request failed");
  return consumeSseStream(res, handlers);
}

export type CopilotStreamHandlers = {
  onStatus?: (text: string) => void;
  onDelta?: (text: string) => void;
  onDone?: (payload: CopilotResponse) => void;
  onError?: (message: string) => void;
};

export async function streamAuditCopilot(
  taskId: string,
  message: string,
  handlers: CopilotStreamHandlers,
  patientId?: string | null,
  userId = "clinician-1",
) {
  const res = await fetch(`${API_BASE}/audit/tasks/${taskId}/copilot/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, patient_id: patientId, user_id: userId }),
  });
  if (!res.ok) await parseError(res, "Copilot request failed");

  const reader = res.body?.getReader();
  if (!reader) throw new Error("Streaming is not supported in this browser.");

  const decoder = new TextDecoder();
  let buffer = "";
  let donePayload: CopilotResponse | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      const line = part.split("\n").find((row) => row.startsWith("data: "));
      if (!line) continue;
      const payload = JSON.parse(line.slice(6)) as Record<string, unknown>;
      const type = payload.type as string | undefined;

      if (type === "status" && typeof payload.content === "string") {
        handlers.onStatus?.(payload.content);
      } else if (type === "delta" && typeof payload.content === "string") {
        handlers.onDelta?.(payload.content);
      } else if (type === "error" && typeof payload.content === "string") {
        handlers.onError?.(payload.content);
        throw new Error(payload.content);
      } else if (type === "done" && typeof payload.reply === "string") {
        donePayload = {
          reply: payload.reply,
          scope: (payload.scope as string) ?? "@Entire_Cohort",
          suggested_chips: (payload.suggested_chips as string[]) ?? [],
          override_applied: Boolean(payload.override_applied),
          updated_patient_id: (payload.updated_patient_id as string | null) ?? null,
          updated_overall_status: (payload.updated_overall_status as string | null) ?? null,
        };
        handlers.onDone?.(donePayload);
      }
    }
  }

  return donePayload;
}

export async function fetchTaskStatus(taskId: string) {
  const id = normalizeTaskId(taskId);
  const res = await fetch(`${API_BASE}/tasks/${id}`, { cache: "no-store" });
  if (!res.ok) await parseError(res, "Task poll failed");
  return res.json() as Promise<TaskStatus>;
}

export async function fetchAuditDashboard(taskId: string) {
  const id = normalizeTaskId(taskId);
  const res = await fetch(`${API_BASE}/audit/tasks/${id}`, { cache: "no-store" });
  if (!res.ok) await parseError(res, "Audit dashboard load failed");
  return res.json() as Promise<AuditDashboard>;
}

export async function sendAuditCopilot(
  taskId: string,
  message: string,
  patientId?: string | null,
  userId = "clinician-1",
) {
  const res = await fetch(`${API_BASE}/audit/tasks/${taskId}/copilot`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, patient_id: patientId, user_id: userId }),
  });
  if (!res.ok) await parseError(res, "Copilot request failed");
  return res.json() as Promise<CopilotResponse>;
}

export async function submitOverride(
  taskId: string,
  payload: {
    patient_id: string;
    trial_id: string;
    encounter_id: string;
    override_status: string;
    override_reason_text: string;
  },
) {
  const res = await fetch(`${API_BASE}/audit/tasks/${taskId}/override`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) await parseError(res, "Override failed");
  return res.json();
}

export async function fetchPatients() {
  const res = await fetch(`${API_BASE}/patients`, { cache: "no-store" });
  if (!res.ok) await parseError(res, "Failed to load patients");
  return res.json() as Promise<string[]>;
}

export async function fetchPatientBiodata(patientId: string) {
  const id = patientId.trim().toUpperCase();
  const res = await fetch(`${API_BASE}/patients/${id}/biodata`, { cache: "no-store" });
  if (!res.ok) await parseError(res, "Failed to load patient biodata");
  return res.json() as Promise<PatientBiodata>;
}

export async function fetchPatient(patientId: string, trialId?: string) {
  const query = trialId ? `?trial_id=${encodeURIComponent(trialId)}` : "";
  const res = await fetch(`${API_BASE}/patients/${patientId}${query}`, { cache: "no-store" });
  if (!res.ok) await parseError(res, "Failed to load patient");
  return res.json() as Promise<PatientSnapshot>;
}

export async function fetchRandomPatient() {
  const res = await fetch(`${API_BASE}/patients/random`, { cache: "no-store" });
  if (!res.ok) await parseError(res, "Random patient failed");
  return res.json() as Promise<RandomPatientResponse>;
}

export async function fetchRandomCriterion() {
  const res = await fetch(`${API_BASE}/criteria/random`, { cache: "no-store" });
  if (!res.ok) await parseError(res, "Random criterion failed");
  return res.json() as Promise<RandomCriterionResponse>;
}

export async function fetchAuditLogs(patientId: string) {
  const res = await fetch(`${API_BASE}/audit/logs/${patientId}`, { cache: "no-store" });
  if (!res.ok) await parseError(res, "Audit logs fetch failed");
  return res.json() as Promise<AuditLogEntry[]>;
}

const TASKS_KEY = "hera_tracked_tasks";

export function loadTrackedTasks(): TrackedTask[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(TASKS_KEY) || "[]");
  } catch {
    return [];
  }
}

export function saveTrackedTasks(tasks: TrackedTask[]) {
  localStorage.setItem(TASKS_KEY, JSON.stringify(tasks.slice(0, 20)));
}

export function upsertTrackedTask(task: TrackedTask) {
  const tasks = loadTrackedTasks().filter((item) => item.task_id !== task.task_id);
  saveTrackedTasks([task, ...tasks]);
}
