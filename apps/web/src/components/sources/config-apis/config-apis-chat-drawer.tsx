"use client";

import { useState, useCallback } from "react";
import { MessageSquare, X, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { useChatWebSocket } from "@/hooks/use-chat-websocket";
import { useChatStore } from "@/stores/chat-store";
import { ChatMessageList } from "@/components/chat/chat-message-list";
import { ChatInput } from "@/components/chat/chat-input";

const SUGGESTIONS = [
  "What loyalty programs are configured?",
  "List all campaigns",
  "Show me coupon series",
  "What messaging channels are set up?",
];

export function ConfigApisChatDrawer() {
  const [isOpen, setIsOpen] = useState(false);
  const { sendMessage, cancelChat } = useChatWebSocket();
  const { activeConversationId, newConversation, messages, isStreaming } =
    useChatStore();

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

  return (
    <>
      {/* Toggle button — visible when drawer is closed */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
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

      {/* Drawer panel */}
      {isOpen && (
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
                onClick={() => setIsOpen(false)}
                className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                title="Close chat"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Chat content */}
          <div className="flex flex-1 flex-col overflow-hidden">
            {/* Show suggestions when no messages and not streaming */}
            {messages.length === 0 && !isStreaming ? (
              <div className="flex flex-1 flex-col items-center justify-center p-6 text-center">
                <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-100 to-purple-100">
                  <MessageSquare className="h-6 w-6 text-violet-600" />
                </div>
                <h4 className="mb-1.5 text-sm font-semibold text-gray-800">
                  Explore Config APIs
                </h4>
                <p className="mb-4 max-w-[280px] text-xs text-gray-500">
                  Ask about loyalty programs, campaigns, coupons, rewards,
                  audiences, or org structure.
                </p>
                <div className="flex flex-wrap justify-center gap-2">
                  {SUGGESTIONS.map((suggestion) => (
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
