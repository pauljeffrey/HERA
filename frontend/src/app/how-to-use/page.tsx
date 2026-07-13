import Link from "next/link";

import InfoPageShell, { InfoStep } from "@/components/InfoPageShell";

export default function HowToUsePage() {
  return (
    <InfoPageShell
      title="How to use HERA"
      subtitle="A short walkthrough for clinicians and researchers exploring trial matching on synthetic patient data."
    >
      <ol className="space-y-4">
        <InfoStep step={1} title="Start a conversation">
          Open the{" "}
          <Link href="/" className="font-medium text-emerald-700 underline">
            Command Center
          </Link>
          . Type trial criteria, ask a population question, or discuss a specific patient. Use the example
          dropdown for ready-made prompts.
        </InfoStep>

        <InfoStep step={2} title="Pick a patient to explore">
          In the left sidebar, expand <strong>Patient roulette</strong> and click <strong>Draw patient</strong>.
          You will see their name, ID, age, sex, specialty, and encounter count. Hit{" "}
          <strong>Discuss this patient</strong> to bind that patient to your chat — then ask about meds, labs,
          trends, or eligibility.
        </InfoStep>

        <InfoStep step={3} title="Run a trial search">
          Paste inclusion and exclusion rules (e.g. LVEF ≤ 35%, age 18–80). Not sure where to start? In the
          sidebar, expand <strong>Criteria roulette</strong> and click <strong>Draw criterion</strong> for a
          random example you can use as-is or adapt — then hit <strong>Use in conversation</strong> to drop it
          into the chat. HERA parses your rules, starts a background search, and gives you an audit link.
          Watch the progress bar in chat or open the audit dashboard from <strong>Recent searches</strong> below
          the roulettes.
        </InfoStep>

        <InfoStep step={4} title="Review the audit dashboard">
          Pick a candidate patient. Read their SOAP timeline, metric matrix, and criterion-by-criterion
          ledger. Toggle the copilot to ask follow-up questions. If you disagree with a verdict, use{" "}
          <strong>Overrule Verdict</strong> and add a short rationale.
        </InfoStep>

        <InfoStep step={5} title="Charts and analytics">
          Ask population questions (“average age?”, “how many mention heart failure?”) or patient-specific
          trends (“plot creatinine over time for PT-000121”). HERA can return tables and inline charts in
          the chat when a visual summary helps.
        </InfoStep>

        <InfoStep step={6} title="Browse individual charts">
          Visit{" "}
          <Link href="/patients" className="font-medium text-emerald-700 underline">
            Patients
          </Link>{" "}
          to open a full chart room outside of a matching task.
        </InfoStep>
      </ol>

      <div className="mt-8 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-7 text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-100">
        <p className="font-semibold">Demo note</p>
        <p className="mt-1">
          This deployment uses smaller backend limits (typically 5–10) for retrieval and deep review so
          responses stay fast. Because this is a demo, search speed, cohort size, and match quality may
          vary and results might be slightly inaccurate compared with a full production configuration.
        </p>
      </div>

      <div className="mt-8 panel">
        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Quick tips</h3>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-7 text-slate-600 dark:text-slate-300">
          <li>Press <kbd className="rounded bg-slate-100 px-1.5 py-0.5 text-xs dark:bg-slate-800">Enter</kbd> to send; <kbd className="rounded bg-slate-100 px-1.5 py-0.5 text-xs dark:bg-slate-800">Shift+Enter</kbd> for a new line.</li>
          <li>Reference a patient by ID (e.g. <code className="text-emerald-700">PT-000121</code>) or by the name shown in patient roulette.</li>
          <li>Read <Link href="/about" className="font-medium text-emerald-700 underline">About</Link> for how the search funnel and tech stack work under the hood.</li>
        </ul>
      </div>
    </InfoPageShell>
  );
}
