"use client";

import { useEffect, useCallback, useMemo } from "react";
import { usePathname } from "next/navigation";
import { MessageSquare, X, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { useChatWebSocket } from "@/hooks/use-chat-websocket";
import { useChatStore } from "@/stores/chat-store";
import { ChatMessageList } from "@/components/chat/chat-message-list";
import { ChatInput } from "@/components/chat/chat-input";

/* ── Per-module suggestion sets ─────────────────────────────────────── */

interface SuggestionSet {
  title: string;
  description: string;
  items: string[];
}

const MODULE_SUGGESTIONS: Record<string, SuggestionSet> = {
  "/dashboard/contexts": {
    title: "Context Management",
    description:
      "Ask about your contexts, create new ones, or refactor existing documents.",
    items: [
      "List my contexts",
      "Create a new context",
      "Refactor all contexts",
      "What contexts do I have?",
    ],
  },
  "/dashboard/sources/config-apis": {
    title: "Explore Config APIs",
    description:
      "Ask about loyalty programs, campaigns, coupons, rewards, audiences, or org structure.",
    items: [
      "What loyalty programs are configured?",
      "List all campaigns",
      "Show me coupon series",
      "What messaging channels are set up?",
    ],
  },
  "/dashboard/sources/databricks": {
    title: "Databricks Source",
    description:
      "Ask about extracted SQL, notebook analysis, or context generation from Databricks.",
    items: [
      "What notebooks have been extracted?",
      "Summarize the SQL patterns found",
      "Help me generate context documents",
    ],
  },
  "/dashboard/sources/confluence": {
    title: "Confluence Source",
    description:
      "Ask about Confluence spaces, pages, or extracted content.",
    items: [
      "What Confluence spaces are available?",
      "Summarize extracted pages",
      "Help me create contexts from Confluence",
    ],
  },
  "/dashboard/context-engine": {
    title: "Context Engine",
    description:
      "Ask about the context tree, node organization, or sync status.",
    items: [
      "Explain the current tree structure",
      "What contexts are in the tree?",
      "Help me understand the hierarchy",
    ],
  },
};

const DEFAULT_SUGGESTIONS: SuggestionSet = {
  title: "Chat with aiRA",
  description:
    "Ask anything about your contexts, data sources, or platform configuration.",
  items: [
    "List my contexts",
    "What data sources are available?",
    "Help me create a context document",
  ],
};

const EXCLUDED_ROUTES = ["/dashboard/chat", "/dashboard/admin"];

/* ── Component ──────────────────────────────────────────────────────── */

export function GlobalChatDrawer() {
  const pathname = usePathname();
  const { sendMessage, cancelChat } = useChatWebSocket();
  const {
    isChatDrawerOpen,
    setChatDrawerOpen,
    pendingMessage,
    clearPendingMessage,
    activeConversationId,
    newConversation,
    messages,
    isStreaming,
  } = useChatStore();

  // Don't render on excluded routes
  const isExcluded = EXCLUDED_ROUTES.some((r) => pathname.startsWith(r));

  // Resolve suggestions for the current route
  const suggestions = useMemo(() => {
    const match = Object.entries(MODULE_SUGGESTIONS).find(([path]) =>
      pathname.startsWith(path)
    );
    return match ? match[1] : DEFAULT_SUGGESTIONS;
  }, [pathname]);

  // Dispatch pending messages (e.g. from ContextPanel "Sanitize All")
  useEffect(() => {
    if (pendingMessage) {
      sendMessage(pendingMessage, activeConversationId);
      clearPendingMessage();
    }
  }, [pendingMessage, sendMessage, activeConversationId, clearPendingMessage]);

  const handleSend = useCallback(
    (content: string) => {
      sendMessage(content, activeConversationId);
    },
    [sendMessage, activeConversationId]
  );

  const handleSuggestion = useCallback(
    (suggestion: string) => {
      sendMessage(suggestion, activeConversationId);
    },
    [sendMessage, activeConversationId]
  );

  if (isExcluded) return null;

  return (
    <>
      {/* Toggle button — visible when drawer is closed */}
      {!isChatDrawerOpen && (
        <button
          onClick={() => setChatDrawerOpen(true)}
          className={cn(
            "fixed bottom-6 right-6 z-50 flex items-center gap-2",
            "rounded-full bg-violet-600 px-4 py-3 text-sm font-medium text-white",
            "shadow-lg transition-all hover:bg-violet-700 hover:shadow-xl",
            "active:scale-95"
          )}
        >
          <MessageSquare className="h-4 w-4" />
          Chat with aiRA
        </button>
      )}

      {/* Drawer panel — flex sibling that shrinks main content */}
      {isChatDrawerOpen && (
        <div
          className={cn(
            "flex h-full w-[420px] shrink-0 flex-col",
            "border-l border-gray-200 bg-white"
          )}
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-purple-600">
                <MessageSquare className="h-3.5 w-3.5 text-white" />
              </div>
              <h3 className="text-sm font-semibold text-gray-800">
                Chat with aiRA
              </h3>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => newConversation()}
                className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700"
                title="New conversation"
              >
                <Plus className="h-3.5 w-3.5" />
                New
              </button>
              <button
                onClick={() => setChatDrawerOpen(false)}
                className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                title="Close chat"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Chat content */}
          <div className="flex flex-1 flex-col overflow-hidden">
            {/* Show route-specific suggestions when no messages */}
            {messages.length === 0 && !isStreaming ? (
              <div className="flex flex-1 flex-col items-center justify-center p-6 text-center">
                <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-100 to-purple-100">
                  <MessageSquare className="h-6 w-6 text-violet-600" />
                </div>
                <h4 className="mb-1.5 text-sm font-semibold text-gray-800">
                  {suggestions.title}
                </h4>
                <p className="mb-4 max-w-[280px] text-xs text-gray-500">
                  {suggestions.description}
                </p>
                <div className="flex flex-wrap justify-center gap-2">
                  {suggestions.items.map((suggestion) => (
                    <button
                      key={suggestion}
                      className="rounded-full border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-600 transition-colors hover:border-violet-300 hover:bg-violet-50 hover:text-violet-700"
                      onClick={() => handleSuggestion(suggestion)}
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <ChatMessageList />
            )}
            <ChatInput onSend={handleSend} onCancel={cancelChat} />
          </div>
        </div>
      )}
    </>
  );
}
