import { extractTaskId } from "@/lib/task_id";

const AUDIT_PATH_RE = /\/audit\/[0-9a-f-]{36}/gi;

function auditLink(id: string) {
  return `[View audit dashboard](/audit/${id.toLowerCase()})`;
}

/** Agent replies mix LaTeX, bare paths, and trailing periods — normalize for ReactMarkdown. */
export function normalizeAssistantMarkdown(text: string): string {
  let out = text;

  out = out.replace(/\$\\le\s*([^$]+)\$/gi, "≤ $1");
  out = out.replace(/\$\\ge\s*([^$]+)\$/gi, "≥ $1");
  out = out.replace(/\$\\lt\s*([^$]+)\$/gi, "< $1");
  out = out.replace(/\$\\gt\s*([^$]+)\$/gi, "> $1");
  out = out.replace(/\\text\{([^}]+)\}/g, "$1");
  out = out.replace(/\\%/g, "%");
  out = out.replace(/\$([^$]+)\$/g, (_, inner: string) => inner.replace(/\\/g, "").trim());
  out = out.replace(/\{,\}/g, ",");
  out = out.replace(/(\d)\s*--\s*(\d)/g, "$1–$2");

  out = out.replace(
    /\[View audit dashboard\]\(\/audit\/([0-9a-f-]{36})(?!\))/gi,
    (_, id: string) => auditLink(id),
  );

  out = out.replace(
    /\[[^\]]*\]\(\/audit\/([0-9a-f-]{36})[.)]*\)/gi,
    (_, id: string) => auditLink(id),
  );

  out = out.replace(
    /(?:here|at|visit|monitor(?:\s+the\s+progress)?|audit)\s*:\s*\/audit\/([0-9a-f-]{36})[.)]*/gi,
    (_, id: string) => auditLink(id),
  );

  out = out.replace(/\/audit\/([0-9a-f-]{36})[.)]*/gi, (match, id: string, offset: number, full: string) => {
    const before = full.slice(Math.max(0, offset - 2), offset);
    if (before === "](") return `/audit/${id.toLowerCase()})`;
    const normalized = id.toLowerCase();
    if (full.includes(`(/audit/${normalized})`)) return "";
    return auditLink(id);
  });

  out = out.replace(/here:\s*(?=\[View audit)/gi, "");
  out = out.replace(/(\[View audit dashboard\]\(\/audit\/[0-9a-f-]{36}\))\s*\1/gi, "$1");

  if (/\[View audit dashboard\]\(\/audit\//i.test(out)) {
    out = out
      .split("\n")
      .filter((line) => !/^\s*\/?audit\/[0-9a-f-]{36}[.)]*\s*$/i.test(line))
      .join("\n");
    out = out.replace(/\s+\/audit\/[0-9a-f-]{36}[.)]*(?=\s|$)/gi, "");
  }

  out = out.replace(/\n{3,}/g, "\n\n");

  return out;
}

export function extractAuditLinks(text: string): string[] {
  const ids = new Set<string>();
  for (const match of text.matchAll(AUDIT_PATH_RE)) {
    const id = extractTaskId(match[0]);
    if (id) ids.add(id);
  }
  return [...ids];
}
