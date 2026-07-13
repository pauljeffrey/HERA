const TASK_ID_RE =
  /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

export function normalizeTaskId(raw: string): string {
  const match = raw.match(TASK_ID_RE);
  if (!match) throw new Error(`Invalid task id: ${raw}`);
  return match[0].toLowerCase();
}

export function extractTaskId(text: string): string | undefined {
  const match = text.match(TASK_ID_RE);
  return match?.[0].toLowerCase();
}

export function extractTrialId(text: string): string | undefined {
  const match = text.match(/TRIAL-[A-Z0-9]+/i);
  return match?.[0].toUpperCase();
}
