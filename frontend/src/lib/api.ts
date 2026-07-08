export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8010/api/v1";

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

async function parseError(res: Response, fallback: string) {
  const text = await res.text();
  throw new Error(text || `${fallback} (${res.status})`);
}

export async function fetchCriteriaPrompts(limit = 20): Promise<CriteriaPromptsResponse> {
  const res = await fetch(`${API_BASE}/criteria/prompts?limit=${limit}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load criteria prompts (${res.status})`);
  return res.json();
}

export async function sendChatMessage(message: string, conversationId?: string | null) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, conversation_id: conversationId ?? undefined }),
  });
  if (!res.ok) await parseError(res, "Chat request failed");
  return res.json() as Promise<ChatResponse>;
}

export async function fetchTaskStatus(taskId: string) {
  const res = await fetch(`${API_BASE}/tasks/${taskId}`, { cache: "no-store" });
  if (!res.ok) await parseError(res, "Task poll failed");
  return res.json() as Promise<TaskStatus>;
}

export async function fetchAuditDashboard(taskId: string) {
  const res = await fetch(`${API_BASE}/audit/tasks/${taskId}`, { cache: "no-store" });
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

export async function fetchPatient(patientId: string, trialId?: string) {
  const query = trialId ? `?trial_id=${encodeURIComponent(trialId)}` : "";
  const res = await fetch(`${API_BASE}/patients/${patientId}${query}`, { cache: "no-store" });
  if (!res.ok) await parseError(res, "Failed to load patient");
  return res.json() as Promise<PatientSnapshot>;
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
