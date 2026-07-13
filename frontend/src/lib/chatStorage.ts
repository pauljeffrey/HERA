export type StoredChatMessage = {
  role: "user" | "assistant";
  content: string;
  taskId?: string;
};

export type StoredChat = {
  conversationId: string | null;
  messages: StoredChatMessage[];
};

export function loadStoredChat(key: string): StoredChat {
  if (typeof window === "undefined") {
    return { conversationId: null, messages: [] };
  }
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return { conversationId: null, messages: [] };
    const parsed = JSON.parse(raw) as StoredChat;
    return {
      conversationId: parsed.conversationId ?? null,
      messages: Array.isArray(parsed.messages) ? parsed.messages : [],
    };
  } catch {
    return { conversationId: null, messages: [] };
  }
}

export function saveStoredChat(key: string, state: StoredChat) {
  if (typeof window === "undefined") return;
  localStorage.setItem(
    key,
    JSON.stringify({
      conversationId: state.conversationId,
      messages: state.messages.slice(-100),
    }),
  );
}

export const COMMAND_CENTER_CHAT_KEY = "hera_command_center_chat";

export function copilotChatKey(taskId: string) {
  return `hera_audit_copilot_${taskId}`;
}
