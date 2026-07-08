"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import ReactMarkdown from "react-markdown";

import CriteriaRoulette from "@/components/explore/CriteriaRoulette";
import TaskSidebar from "@/components/TaskSidebar";
import {
  CRITERIA_SEED_KEY,
  fetchCriteriaPrompts,
  loadTrackedTasks,
  sendChatMessage,
  type TrackedTask,
} from "@/lib/api";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  taskId?: string;
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

  const handleTasksChange = useCallback((updated: TrackedTask[]) => {
    setTasks(updated);
  }, []);

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
    const nextMessages: ChatMessage[] = [...messages, { role: "user", content: text }];
    setMessages(nextMessages);
    setInput("");

    try {
      const response = await sendChatMessage(text, conversationId);
      setConversationId(response.conversation_id);
      setMessages((prev) => [...prev, { role: "assistant", content: response.reply }]);
    } catch (err) {
      setError(friendlyError(err));
      setMessages((prev) => prev.slice(0, -1));
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

  const busy = loading;
  const rouletteOpen = searchParams.get("roulette") === "1";

  return (
    <div className="flex min-h-[calc(100vh-49px)] flex-col bg-slate-100 dark:bg-slate-950">
      <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col lg:flex-row">
        <aside className="w-full shrink-0 border-b border-slate-200/70 bg-white/80 dark:border-slate-800 dark:bg-slate-950/80 lg:w-80 lg:border-b-0 lg:border-r">
          <TaskSidebar tasks={tasks} onTasksChange={handleTasksChange} />
        </aside>

        <div className="flex min-h-0 flex-1 flex-col">
          <CriteriaRoulette
            embedded
            defaultOpen={rouletteOpen}
            onUseCriterion={(text) => insertPrompt(`Help me screen patients with these criteria:\n${text}`)}
          />

          <div className="flex min-h-0 flex-1 flex-col">
            <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
              {messages.length === 0 ? (
                <div className="mx-auto max-w-2xl pt-8 text-center">
                  <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-700 text-xl font-semibold text-white">
                    H
                  </div>
                  <h1 className="page-title">Clinical command center</h1>
                  <p className="mt-3 text-sm leading-7 text-slate-600 dark:text-slate-400">{WELCOME}</p>
                </div>
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
                          ) : (
                            <div className="prose prose-sm max-w-none dark:prose-invert">
                              <ReactMarkdown>{message.content}</ReactMarkdown>
                            </div>
                          )}
                          {liveTask && !["completed", "failed"].includes(liveTask.status) ? (
                            <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
                              <p>Searching cohort… {liveTask.progress_percentage}%</p>
                              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-amber-100 dark:bg-amber-900/50">
                                <div
                                  className="h-full rounded-full bg-amber-500 transition-all duration-300"
                                  style={{ width: `${liveTask.progress_percentage}%` }}
                                />
                              </div>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    );
                  })}
                  {loading ? (
                    <div className="flex gap-3">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-700 text-xs font-semibold text-white">
                        H
                      </div>
                      <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900">
                        Thinking…
                      </div>
                    </div>
                  ) : null}
                  <div ref={bottomRef} />
                </div>
              )}
            </div>

            <div className="border-t border-slate-200/70 bg-white/95 px-4 py-4 backdrop-blur dark:border-slate-800 dark:bg-slate-950/95 sm:px-6">
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
  if (/OPENAI_API_KEY|MODEL_API_KEY|Chat agent failed/i.test(message)) {
    return "Chat is unavailable right now. Check that the server has an API key configured.";
  }
  if (/failed to fetch|network/i.test(message)) {
    return "Could not reach the server. Make sure the backend is running.";
  }
  if (message.startsWith("{")) return "Something went wrong. Please try again.";
  return message.length > 180 ? "Something went wrong. Please try again." : message;
}
