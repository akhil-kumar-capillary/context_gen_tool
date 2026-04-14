"use client";

import { useEffect, useCallback, useMemo } from "react";
import { usePathname } from "next/navigation";
import { MessageSquare, X, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { useChatWebSocket } from "@/hooks/use-chat-websocket";
import { useChatStore } from "@/stores/chat-store";
import { useContextStore } from "@/stores/context-store";
import { ChatMessageList } from "@/components/chat/chat-message-list";
import { ChatInput } from "@/components/chat/chat-input";

/* ── Module detection ──────────────────────────────────────────────── */

/** Map pathname prefixes to module identifiers sent to the backend. */
const PATHNAME_TO_MODULE: Record<string, string> = {
  "/dashboard/context-engine": "context_engine",
  "/dashboard/contexts": "context_management",
  "/dashboard/sources/config-apis": "config_apis",
  "/dashboard/sources/databricks": "databricks",
  "/dashboard/sources/confluence": "confluence",
};

function resolveCurrentModule(pathname: string): string | null {
  const match = Object.entries(PATHNAME_TO_MODULE).find(([prefix]) =>
    pathname.startsWith(prefix)
  );
  return match ? match[1] : null;
}

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

  // Hide chat bubble when a context drawer/overlay is open
  const { editingContextId, isCreating, versionHistoryContextId } = useContextStore();
  const hasOverlayOpen = !!(editingContextId || isCreating || versionHistoryContextId);

  // Don't render on excluded routes
  const isExcluded = EXCLUDED_ROUTES.some((r) => pathname.startsWith(r));

  // Resolve the current module for the chat backend
  const currentModule = useMemo(() => resolveCurrentModule(pathname), [pathname]);

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
      sendMessage(pendingMessage, activeConversationId, currentModule);
      clearPendingMessage();
    }
  }, [pendingMessage, sendMessage, activeConversationId, clearPendingMessage, currentModule]);

  const handleSend = useCallback(
    (content: string) => {
      sendMessage(content, activeConversationId, currentModule);
    },
    [sendMessage, activeConversationId, currentModule]
  );

  const handleSuggestion = useCallback(
    (suggestion: string) => {
      sendMessage(suggestion, activeConversationId, currentModule);
    },
    [sendMessage, activeConversationId, currentModule]
  );

  if (isExcluded) return null;

  return (
    <>
      {/* Toggle button — hidden when chat is open or an overlay drawer is open */}
      {!isChatDrawerOpen && !hasOverlayOpen && (
        <button
          onClick={() => setChatDrawerOpen(true)}
          className={cn(
            "fixed bottom-3 right-3 z-50 flex items-center gap-2",
            "rounded-full bg-primary px-3.5 py-2.5 text-xs font-semibold text-primary-foreground",
            "shadow-lg transition-all hover:bg-primary/90 hover:shadow-xl",
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
            "flex h-full w-full lg:w-[520px] shrink-0 flex-col",
            "border-l border-border bg-background",
          )}
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary">
                <MessageSquare className="h-3.5 w-3.5 text-primary-foreground" />
              </div>
              <h3 className="text-sm font-semibold text-foreground">
                Chat with aiRA
              </h3>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => newConversation()}
                className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                title="New conversation"
              >
                <Plus className="h-3.5 w-3.5" />
                New
              </button>
              <button
                onClick={() => setChatDrawerOpen(false)}
                className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                title="Close chat"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Chat content */}
          <div className="flex flex-1 flex-col overflow-hidden">
            {messages.length === 0 && !isStreaming ? (
              <div className="flex flex-1 flex-col items-center justify-center p-6 text-center">
                <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10">
                  <MessageSquare className="h-6 w-6 text-primary" />
                </div>
                <h4 className="mb-1.5 text-sm font-semibold text-foreground">
                  {suggestions.title}
                </h4>
                <p className="mb-4 max-w-[300px] text-xs text-muted-foreground">
                  {suggestions.description}
                </p>
                <div className="flex flex-wrap justify-center gap-2">
                  {suggestions.items.map((suggestion) => (
                    <button
                      key={suggestion}
                      className="rounded-full border border-border bg-background px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary"
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
