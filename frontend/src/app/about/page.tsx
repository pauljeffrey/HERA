import InfoPageShell, { InfoCard } from "@/components/InfoPageShell";

export default function AboutPage() {
  return (
    <InfoPageShell
      title="About HERA"
      subtitle="Healthcare Eligibility & Reasoning Agent, a decision-support assistant that helps clinicians explore synthetic patient records and screen for clinical trial fit."
    >
      <div className="space-y-6">
        <InfoCard title="What it does" icon="🎯">
          <p>
            HERA helps you find patients who may match a trial protocol. You describe inclusion and
            exclusion rules in plain language. HERA searches the electronic health record, narrows the
            cohort, and explains its reasoning for each candidate.
          </p>
          <p>
            You stay in control. HERA suggests matches and cites chart evidence. It does not replace
            clinical judgment or formal eligibility sign-off.
          </p>
        </InfoCard>

        <InfoCard title="How the search works" icon="🔍">
          <p>HERA uses a three-stage funnel so searches stay fast but thorough:</p>
          <ol className="list-decimal space-y-2 pl-5">
            <li>
              <strong>Keyword search (FTS)</strong>: scans notes and investigations for clinical terms
              you specify (e.g. “heart failure”, “LVEF”). Casts a wide net quickly.
            </li>
            <li>
              <strong>Semantic search (vectors)</strong>: understands meaning, not just exact words.
              Multiple rephrasings of your criteria are tried so different note styles still match.
            </li>
            <li>
              <strong>Deep review (agentic)</strong>: an AI agent reads each shortlisted patient’s chart,
              checks every criterion, and produces a structured verdict with quoted evidence.
            </li>
          </ol>
          <p>
            Keyword and semantic search run <strong>at the same time</strong>. Their results are merged,
            duplicate note hits are dropped, and survivors are <strong>re-ranked</strong> (including a math
            guard for numeric cut-offs). Only the top few unique patients are passed to the LLM for full
            chart review — capped to keep cost and response time reasonable on this demo server (a single
            8&nbsp;GB / 4-CPU machine).
          </p>
        </InfoCard>

        <InfoCard title="Synthetic data & Supabase" icon="🧬">
          <p>
            All patients in this demo are generated and not real EHR records. The pipeline has three stages:
          </p>
          <ol className="list-decimal space-y-2 pl-5">
            <li>
              <strong>Structured trajectories</strong> (<code className="text-xs">clinical_data_gen/structured_clinical_data</code>{" "})
              uses the OpenAI Batch API to produce longitudinal patient JSON: demographics, encounters,
              diagnoses, medications, labs, and investigations across cardiovascular, oncology, and ICU
              specialties.
            </li>
            <li>
              <strong>SOAP notes</strong>(<code className="text-xs">clinical_data_gen/soap_notes</code>{" "})
              converts each structured encounter into unstructured SOAP progress notes (again via Batch API),
              so the search funnel has realistic clinical prose to index.
            </li>
            <li>
              <strong>Load into Supabase</strong>(<code className="text-xs">backend/app/db/schema.sql</code>{" "})
              defines the Postgres tables. On startup, the backend prepopulate service reads the generated
              JSON datasets and upserts rows into Supabase over the REST API. A separate embedding
              ingest step (<code className="text-xs">scripts/ingest_ehr</code>) chunks those notes and
              indexes them in Pinecone (or pgvector) for semantic search.
            </li>
          </ol>
          <p>
            Paths to the canonical JSON files are configured via{" "}
            <code className="text-xs">PATIENT_TRAJECTORIES_PATH</code> and{" "}
            <code className="text-xs">SOAP_NOTES_PATH</code> in the backend environment.
          </p>
        </InfoCard>

        <InfoCard title="System design (simple view)" icon="🏗️">
          <ul className="list-disc space-y-2 pl-5">
            <li>
              <strong>Command Center</strong> : chat interface where you ask questions, start searches, or
              explore individual patients.
            </li>
            <li>
              <strong>Matching pipeline</strong> : runs in the background after you dispatch a search;
              progress is tracked by task ID.
            </li>
            <li>
              <strong>Audit dashboard</strong> (four-pane view) :  chart timeline, metrics, eligibility
              ledger, and an optional copilot for follow-up questions.
            </li>
            <li>
              <strong>Audit log</strong> : clinician overrides and agent responses are stored for
              traceability.
            </li>
          </ul>
        </InfoCard>

        <InfoCard title="Tech stack" icon="⚙️">
          <ul className="grid gap-2 sm:grid-cols-2">
            <li className="panel-row text-sm">
              <span className="panel-label">Frontend</span>
              <p className="mt-1 text-slate-800 dark:text-slate-100">Next.js, React, Tailwind</p>
            </li>
            <li className="panel-row text-sm">
              <span className="panel-label">Backend</span>
              <p className="mt-1 text-slate-800 dark:text-slate-100">FastAPI, Pydantic AI agents</p>
            </li>
            <li className="panel-row text-sm">
              <span className="panel-label">Database</span>
              <p className="mt-1 text-slate-800 dark:text-slate-100">Supabase / Postgres + pgvector</p>
            </li>
            <li className="panel-row text-sm">
              <span className="panel-label">LLM routing</span>
              <p className="mt-1 text-slate-800 dark:text-slate-100">OpenRouter / OpenAI-compatible APIs</p>
            </li>
            <li className="panel-row text-sm">
              <span className="panel-label">Task state</span>
              <p className="mt-1 text-slate-800 dark:text-slate-100">Redis for chat history & progress</p>
            </li>
            <li className="panel-row text-sm">
              <span className="panel-label">Charts</span>
              <p className="mt-1 text-slate-800 dark:text-slate-100">Matplotlib PNGs served from the API</p>
            </li>
          </ul>
        </InfoCard>

        <InfoCard title="Trade-offs & considerations" icon="⚖️">
          <ul className="list-disc space-y-2 pl-5">
            <li>
              <strong>Demo tuning</strong>: This deployment uses smaller backend limits (typically in the
              5–10 range) so searches return faster. Deep review is hard-capped by{" "}
              <code className="text-xs">TIER3_PATIENT_CAP</code> (
              <code className="text-xs">min(n_candidates, TIER3_PATIENT_CAP)</code> patients reach the
              analysis agent). Retrieval limits may also be reduced. Results and performance may vary and can
              be slightly less accurate than a full production run.
            </li>
            <li>
              <strong>Speed vs. depth</strong>: The funnel caps how many patients get a full chart review
              so responses stay practical; very large cohorts may need stricter criteria.
            </li>
            <li>
              <strong>Recall vs. precision</strong>: Semantic search casts a wider net; the deep review
              step filters false positives but adds latency.
            </li>
            <li>
              <strong>Synthetic data only</strong>: All patients in this demo are generated; behaviour on
              real EHR data would need validation and governance.
            </li>
            <li>
              <strong>LLM variability</strong>: Models can misread ambiguous notes; the audit dashboard and
              override flow exist so humans can correct mistakes.
            </li>
            <li>
              <strong>Privacy</strong>: Designed for de-identified research settings; production use would
              require HIPAA-grade controls and access policies.
            </li>
          </ul>
        </InfoCard>

        <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-6 text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-100">
          HERA is a research and decision-support prototype. Not for clinical use without proper validation,
          regulatory review, and institutional approval.
        </p>
      </div>
    </InfoPageShell>
  );
}
