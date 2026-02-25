import { create } from "zustand";
import type { ChatMessage, ChatConversation, ToolCallStatus, LLMUsage } from "@/types";

interface ChatState {
  // Conversation list
  conversations: ChatConversation[];
  activeConversationId: string | null;

  // Current conversation messages
  messages: ChatMessage[];

  // Streaming state
  isStreaming: boolean;
  streamingText: string;
  activeToolCalls: ToolCallStatus[];

  // Actions — conversation management
  setConversations: (conversations: ChatConversation[]) => void;
  setActiveConversation: (id: string | null) => void;
  addConversation: (conv: ChatConversation) => void;
  removeConversation: (id: string) => void;

  // Actions — messages
  setMessages: (messages: ChatMessage[]) => void;
  addMessage: (message: ChatMessage) => void;

  // Actions — streaming
  startStreaming: () => void;
  appendChunk: (text: string) => void;
  addToolCall: (tool: ToolCallStatus) => void;
  updateToolCallStatus: (toolId: string, status: ToolCallStatus["status"], display?: string) => void;
  completeToolCall: (toolId: string, summary: string) => void;
  finishStreaming: (conversationId: string, usage?: LLMUsage, toolCalls?: ToolCallStatus[], error?: string) => void;

  // Actions — new chat
  newConversation: () => void;
}

export const useChatStore = create<ChatState>()((set, get) => ({
  conversations: [],
  activeConversationId: null,
  messages: [],
  isStreaming: false,
  streamingText: "",
  activeToolCalls: [],

  // --- Conversation management ---

  setConversations: (conversations) => set({ conversations }),

  setActiveConversation: (id) => set({ activeConversationId: id }),

  addConversation: (conv) =>
    set((state) => ({
      conversations: [conv, ...state.conversations.filter((c) => c.id !== conv.id)],
    })),

  removeConversation: (id) =>
    set((state) => ({
      conversations: state.conversations.filter((c) => c.id !== id),
      activeConversationId:
        state.activeConversationId === id ? null : state.activeConversationId,
      messages: state.activeConversationId === id ? [] : state.messages,
    })),

  // --- Messages ---

  setMessages: (messages) => set({ messages }),

  addMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),

  // --- Streaming ---

  startStreaming: () =>
    set({ isStreaming: true, streamingText: "", activeToolCalls: [] }),

  appendChunk: (text) =>
    set((state) => ({ streamingText: state.streamingText + text })),

  addToolCall: (tool) =>
    set((state) => ({
      activeToolCalls: [...state.activeToolCalls, tool],
    })),

  updateToolCallStatus: (toolId, status, display) =>
    set((state) => ({
      activeToolCalls: state.activeToolCalls.map((tc) =>
        tc.id === toolId ? { ...tc, status, ...(display ? { display } : {}) } : tc
      ),
    })),

  completeToolCall: (toolId, summary) =>
    set((state) => ({
      activeToolCalls: state.activeToolCalls.map((tc) =>
        tc.id === toolId ? { ...tc, status: "done" as const, summary } : tc
      ),
    })),

  finishStreaming: (conversationId, usage, toolCalls, error) => {
    const { isStreaming, streamingText, activeToolCalls } = get();
    if (!isStreaming) return; // Idempotency guard — prevent duplicate assistant messages

    // Create the assistant message from streamed content
    const assistantMessage: ChatMessage = {
      id: crypto.randomUUID(),
      conversationId,
      role: "assistant",
      content: streamingText || (error ? "" : ""),
      toolCalls: toolCalls || activeToolCalls,
      tokenUsage: usage,
      error,
      createdAt: new Date().toISOString(),
    };

    set((state) => ({
      isStreaming: false,
      streamingText: "",
      activeToolCalls: [],
      messages: [...state.messages, assistantMessage],
      // Update conversation in the list
      activeConversationId: conversationId || state.activeConversationId,
    }));
  },

  // --- New chat ---

  newConversation: () =>
    set({
      activeConversationId: null,
      messages: [],
      isStreaming: false,
      streamingText: "",
      activeToolCalls: [],
    }),
}));
