"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import CriteriaRoulette from "@/components/explore/CriteriaRoulette";
import PatientRoulette from "@/components/explore/PatientRoulette";
import ChatMarkdown from "@/components/ChatMarkdown";
import TaskProgressBar from "@/components/TaskProgressBar";
import TaskSidebar from "@/components/TaskSidebar";
import {
  COMMAND_CENTER_CHAT_KEY,
  loadStoredChat,
  saveStoredChat,
  type StoredChatMessage,
} from "@/lib/chatStorage";
import {
  CRITERIA_SEED_KEY,
  fetchCriteriaPrompts,
  loadTrackedTasks,
  streamChatMessage,
  upsertTrackedTask,
  type PatientBiodata,
  type TrackedTask,
} from "@/lib/api";
import { extractTaskId, extractTrialId } from "@/lib/task_id";

type ChatMessage = StoredChatMessage & {
  streaming?: boolean;
  statusText?: string;
};

const WELCOME =
  "I'm your HERA assistant. Ask clinical questions, explore trial criteria, or paste inclusion and exclusion rules — I'll help you think through them.";

export default function CommandCenter() {
  const searchParams = useSearchParams();
  const bottomRef = useRef<HTMLDivElement>(null);
  const [tasks, setTasks] = useState<TrackedTask[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [prompts, setPrompts] = useState<{ text: string; patient_count: number }[]>([]);
  const [activePatient, setActivePatient] = useState<PatientBiodata | null>(null);
  const [hydrated, setHydrated] = useState(false);

  const handleTasksChange = useCallback((updated: TrackedTask[]) => {
    setTasks(updated);
  }, []);

  useEffect(() => {
    const stored = loadStoredChat(COMMAND_CENTER_CHAT_KEY);
    setMessages(stored.messages);
    setConversationId(stored.conversationId);
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    saveStoredChat(COMMAND_CENTER_CHAT_KEY, {
      conversationId,
      messages: messages.map(({ role, content, taskId }) => ({ role, content, taskId })),
    });
  }, [conversationId, messages, hydrated]);

  useEffect(() => {
    setTasks(loadTrackedTasks());
    fetchCriteriaPrompts()
      .then((data) => setPrompts(data.prompts))
      .catch(() => undefined);

    const urlSeed = searchParams.get("seed");
    const storedSeed = typeof window !== "undefined" ? sessionStorage.getItem(CRITERIA_SEED_KEY) : null;
    const seed = urlSeed || storedSeed;
    if (seed) {
      setInput(seed);
      if (storedSeed) sessionStorage.removeItem(CRITERIA_SEED_KEY);
    }
  }, [searchParams]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleChatSubmit(event: React.FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    setLoading(true);
    setError(null);
    const assistantIndex = messages.length + 1;
    setMessages((prev) => [
      ...prev,
      { role: "user", content: text },
      { role: "assistant", content: "", streaming: true, statusText: "thinking..." },
    ]);
    setInput("");

    try {
      const response = await streamChatMessage(
        text,
        {
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
        },
        conversationId,
        activePatient?.patient_id,
      );

      if (!response) {
        throw new Error("Chat ended without a response.");
      }

      setConversationId(response.conversation_id);
      const taskId = extractTaskId(response.reply);
      const trialId = extractTrialId(response.reply) ?? "UNKNOWN";
      if (taskId) {
        const tracked: TrackedTask = {
          task_id: taskId,
          trial_id: trialId,
          status: "processing",
          progress_percentage: 10,
          response: response.reply.slice(0, 240),
        };
        upsertTrackedTask(tracked);
        setTasks(loadTrackedTasks());
      }

      setMessages((prev) => {
        const next = [...prev];
        next[assistantIndex] = {
          role: "assistant",
          content: response.reply,
          taskId,
        };
        return next;
      });
    } catch (err) {
      setError(friendlyError(err));
      setMessages((prev) => prev.slice(0, -2));
      setInput(text);
    } finally {
      setLoading(false);
    }
  }

  function taskProgress(taskId: string | undefined) {
    if (!taskId) return null;
    return tasks.find((task) => task.task_id === taskId);
  }

  function insertPrompt(text: string) {
    setInput((prev) => (prev ? `${prev.trim()}\n\n${text}` : text));
  }

  function bindPatient(patient: PatientBiodata) {
    setActivePatient(patient);
    insertPrompt(
      `I'd like to discuss patient ${patient.patient_id} (${patient.name}, ${patient.age}y ${patient.sex}, ${patient.encounter_count} encounters).`,
    );
  }

  const busy = loading;
  const rouletteOpen = searchParams.get("roulette") === "1";

  return (
    <div className="flex h-[calc(100vh-49px)] overflow-hidden bg-slate-100 dark:bg-slate-950">
      <div className="mx-auto flex h-full w-full max-w-7xl flex-col lg:flex-row">
        <aside className="max-h-44 w-full shrink-0 overflow-y-auto border-b border-slate-200/70 bg-white/80 dark:border-slate-800 dark:bg-slate-950/80 lg:h-full lg:max-h-none lg:w-80 lg:border-b-0 lg:border-r">
          <TaskSidebar tasks={tasks} onTasksChange={handleTasksChange} />
        </aside>

        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <CriteriaRoulette
            embedded
            defaultOpen={rouletteOpen}
            onUseCriterion={(text) => insertPrompt(`Help me screen patients with these criteria:\n${text}`)}
          />

          <PatientRoulette embedded onUsePatient={bindPatient} />

          {activePatient ? (
            <div className="border-b border-emerald-200/70 bg-emerald-50/60 px-4 py-2 text-xs text-emerald-900 dark:border-emerald-900/40 dark:bg-emerald-950/30 dark:text-emerald-100">
              Chat bound to{" "}
              <span className="font-semibold">
                {activePatient.name} ({activePatient.patient_id})
              </span>
              <button
                type="button"
                onClick={() => setActivePatient(null)}
                className="ml-3 underline hover:no-underline"
              >
                Clear
              </button>
            </div>
          ) : null}

          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <div className="shrink-0 border-b border-slate-200/70 bg-white/80 px-4 py-2 dark:border-slate-800 dark:bg-slate-950/80 sm:px-6">
              <div className="mx-auto flex max-w-2xl items-center gap-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-700 text-xs font-semibold text-white">
                  H
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">Clinical command center</p>
                  <p className="truncate text-xs text-slate-500">{WELCOME}</p>
                </div>
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-6">
              {messages.length === 0 ? (
                <p className="mx-auto max-w-2xl text-center text-xs text-slate-400">
                  Start a conversation below, or use patient roulette and example criteria.
                </p>
              ) : (
                <div className="mx-auto flex max-w-2xl flex-col gap-4">
                  {messages.map((message, index) => {
                    const liveTask = taskProgress(message.taskId);
                    const isUser = message.role === "user";
                    return (
                      <div
                        key={`${message.role}-${index}`}
                        className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"}`}
                      >
                        {!isUser ? (
                          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-700 text-xs font-semibold text-white">
                            H
                          </div>
                        ) : null}
                        <div
                          className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-6 ${
                            isUser
                              ? "bg-emerald-700 text-white"
                              : "border border-slate-200 bg-white text-slate-800 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100"
                          }`}
                        >
                          {isUser ? (
                            <p className="whitespace-pre-wrap">{message.content}</p>
                          ) : message.streaming && !message.content ? (
                            <p className="text-slate-500">{message.statusText ?? "thinking..."}</p>
                          ) : (
                            <div className="prose prose-sm max-w-none dark:prose-invert">
                              <ChatMarkdown content={message.content || "…"} />
                            </div>
                          )}
                          {liveTask && !["completed", "failed"].includes(liveTask.status) ? (
                            <div className="mt-3">
                              <TaskProgressBar
                                progress={liveTask.progress_percentage}
                                label="Searching cohort"
                              />
                            </div>
                          ) : null}
                        </div>
                      </div>
                    );
                  })}
                  <div ref={bottomRef} />
                </div>
              )}
            </div>

            <div className="shrink-0 border-t border-slate-200/70 bg-white/95 px-4 py-4 backdrop-blur dark:border-slate-800 dark:bg-slate-950/95 sm:px-6">
              <div className="mx-auto max-w-2xl">
                {prompts.length ? (
                  <select
                    className="mb-3 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                    defaultValue=""
                    onChange={(event) => {
                      if (event.target.value) insertPrompt(event.target.value);
                      event.target.value = "";
                    }}
                  >
                    <option value="">Insert example criteria…</option>
                    {prompts.map((prompt) => (
                      <option key={prompt.text} value={prompt.text}>
                        {prompt.text.slice(0, 90)}
                        {prompt.text.length > 90 ? "…" : ""}
                      </option>
                    ))}
                  </select>
                ) : null}

                {error ? <p className="mb-2 text-sm text-red-600">{error}</p> : null}

                <form onSubmit={handleChatSubmit} className="flex flex-col gap-2 sm:flex-row sm:items-end">
                  <textarea
                    value={input}
                    onChange={(event) => setInput(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        event.currentTarget.form?.requestSubmit();
                      }
                    }}
                    rows={2}
                    placeholder="Message HERA…"
                    className="min-h-[52px] flex-1 resize-none rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none ring-emerald-600 focus:ring-2 dark:border-slate-700 dark:bg-slate-900"
                  />
                  <button
                    type="submit"
                    disabled={busy || !input.trim()}
                    className="shrink-0 rounded-xl bg-emerald-700 px-5 py-3 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-40"
                  >
                    {loading ? "Sending…" : "Send"}
                  </button>
                </form>
                <p className="mt-2 text-xs text-slate-400">Enter to send · Shift+Enter for a new line</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function friendlyError(err: unknown) {
  if (!(err instanceof Error)) return "Something went wrong. Please try again.";
  const message = err.message;
  if (/rate-limited|429/i.test(message)) {
    return "The AI provider is temporarily rate-limited. Please wait a minute and try again.";
  }
  if (/MODEL_API_KEY|authentication failed|401|403/i.test(message)) {
    return "Chat is unavailable: the server model API key is missing or invalid.";
  }
  if (/failed to fetch|network/i.test(message)) {
    return "Could not reach the server. Make sure the backend is running.";
  }
  if (/Chat agent failed \(HTTP/i.test(message)) {
    return message.replace(/^Chat agent failed \(HTTP \d+\)\.$/, "The chat agent failed. Please try again.");
  }
  if (message.startsWith("{")) return "Something went wrong. Please try again.";
  return message.length > 220 ? "Something went wrong. Please try again." : message;
}
