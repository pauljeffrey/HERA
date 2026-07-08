"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";

import { sendAuditCopilot } from "@/lib/api";
import { useAuditContext } from "@/context/AuditContext";

type CopilotMessage = { role: "user" | "assistant"; content: string };

export default function CopilotPane({
  taskId,
  onPatientUpdate,
}: {
  taskId: string;
  onPatientUpdate: () => void;
}) {
  const { selectedPatientId } = useAuditContext();
  const [messages, setMessages] = useState<CopilotMessage[]>([]);
  const [chips, setChips] = useState<string[]>([]);
  const [scope, setScope] = useState("@Entire_Cohort");
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  async function sendMessage(text: string) {
    if (!text.trim() || loading) return;
    setLoading(true);
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");

    try {
      const response = await sendAuditCopilot(taskId, text, selectedPatientId);
      setScope(response.scope);
      setChips(response.suggested_chips);
      setMessages((prev) => [...prev, { role: "assistant", content: response.reply }]);
      if (response.override_applied) onPatientUpdate();
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: err instanceof Error ? err.message : "Copilot failed" },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">HERA Copilot</p>
          <p className="text-xs text-emerald-700">{scope}</p>
        </div>
      </div>

      <div className="panel-row flex-1 space-y-3 overflow-y-auto">
        {messages.map((message, index) => (
          <div
            key={`${message.role}-${index}`}
            className={`rounded-lg px-3 py-2 text-sm ${
              message.role === "user" ? "bg-emerald-50 text-emerald-950" : "bg-slate-100 dark:bg-slate-800"
            }`}
          >
            {message.role === "assistant" ? <ReactMarkdown>{message.content}</ReactMarkdown> : message.content}
          </div>
        ))}
      </div>

      {chips.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {chips.map((chip) => (
            <button
              key={chip}
              type="button"
              onClick={() => sendMessage(chip)}
              className="rounded-full border border-slate-300 px-3 py-1 text-xs hover:border-emerald-500 dark:border-slate-700"
            >
              {chip}
            </button>
          ))}
        </div>
      ) : null}

      <form
        className="mt-3 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          sendMessage(input);
        }}
      >
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask a question…"
          className="field-input flex-1"
        />
        <button type="submit" disabled={loading || !input.trim()} className="btn-primary">
          Send
        </button>
      </form>
    </div>
  );
}
