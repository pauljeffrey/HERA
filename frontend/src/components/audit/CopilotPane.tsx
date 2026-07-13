"use client";

import { useEffect, useRef, useState } from "react";

import ChatMarkdown from "@/components/ChatMarkdown";
import { copilotChatKey, loadStoredChat, saveStoredChat } from "@/lib/chatStorage";
import { streamAuditCopilot } from "@/lib/api";
import { useAuditContext } from "@/context/AuditContext";

type CopilotMessage = { role: "user" | "assistant"; content: string; streaming?: boolean; statusText?: string };

export default function CopilotPane({
  taskId,
  onPatientUpdate,
}: {
  taskId: string;
  onPatientUpdate: () => void;
}) {
  const { selectedPatientId } = useAuditContext();
  const storageKey = copilotChatKey(taskId);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [messages, setMessages] = useState<CopilotMessage[]>([]);
  const [chips, setChips] = useState<string[]>([]);
  const [scope, setScope] = useState("@Entire_Cohort");
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const stored = loadStoredChat(storageKey);
    setMessages(stored.messages);
    setHydrated(true);
  }, [storageKey]);

  useEffect(() => {
    if (!hydrated) return;
    saveStoredChat(storageKey, { conversationId: null, messages });
  }, [hydrated, messages, storageKey]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function sendMessage(text: string) {
    if (!text.trim() || loading) return;
    setLoading(true);
    const userIndex = messages.length;
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    const assistantIndex = userIndex + 1;
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", streaming: true, statusText: "Thinking…" },
    ]);
    setInput("");

    try {
      await streamAuditCopilot(
        taskId,
        text,
        {
          onStatus: (status) => {
            setMessages((prev) => {
              const next = [...prev];
              const row = next[assistantIndex];
              if (row?.role === "assistant") {
                next[assistantIndex] = { ...row, statusText: status };
              }
              return next;
            });
          },
          onDelta: (delta) => {
            setMessages((prev) => {
              const next = [...prev];
              const row = next[assistantIndex];
              if (row?.role === "assistant") {
                next[assistantIndex] = {
                  ...row,
                  content: row.content + delta,
                  statusText: undefined,
                };
              }
              return next;
            });
          },
          onDone: (response) => {
            setScope(response.scope);
            setChips(response.suggested_chips);
            setMessages((prev) => {
              const next = [...prev];
              next[assistantIndex] = { role: "assistant", content: response.reply };
              return next;
            });
            if (response.override_applied) onPatientUpdate();
          },
        },
        selectedPatientId,
      );
    } catch (err) {
      setMessages((prev) => {
        const next = [...prev];
        next[assistantIndex] = {
          role: "assistant",
          content: err instanceof Error ? err.message : "Copilot failed",
        };
        return next;
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-3 shrink-0 flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">HERA Copilot</p>
          <p className="text-xs text-emerald-700">{scope}</p>
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
        {messages.map((message, index) => (
          <div
            key={`${message.role}-${index}`}
            className={`rounded-lg px-3 py-2 text-sm ${
              message.role === "user" ? "bg-emerald-50 text-emerald-950" : "bg-slate-100 dark:bg-slate-800"
            }`}
          >
            {message.role === "assistant" ? (
              message.streaming && !message.content ? (
                <p className="text-slate-500">{message.statusText ?? "Thinking…"}</p>
              ) : (
                <div className="prose prose-sm max-w-none dark:prose-invert">
                  <ChatMarkdown content={message.content || "…"} />
                </div>
              )
            ) : (
              <p className="whitespace-pre-wrap">{message.content}</p>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {chips.length ? (
        <div className="mt-3 flex shrink-0 flex-wrap gap-2">
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
        className="mt-3 flex shrink-0 gap-2"
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
