"use client";

import { useCallback } from "react";
import { useChatStore } from "@/stores/chat-store";
import { useChatWebSocket } from "@/hooks/use-chat-websocket";
import { ContextPanel } from "@/components/contexts/context-panel";
import { ChatMessageList } from "@/components/chat/chat-message-list";
import { ChatInput } from "@/components/chat/chat-input";

export default function ContextsPage() {
  const { activeConversationId } = useChatStore();
  const { sendMessage } = useChatWebSocket();

  const handleSend = useCallback(
    (content: string) => {
      sendMessage(content, activeConversationId);
    },
    [sendMessage, activeConversationId]
  );

  return (
    <div className="-m-6 flex h-[calc(100vh-3.5rem)]">
      {/* Context Panel — left */}
      <div className="w-[62%] overflow-y-auto border-r border-gray-200 p-6">
        <ContextPanel onSendChatMessage={handleSend} />
      </div>

      {/* Chat Panel — right */}
      <div className="flex w-[38%] flex-col overflow-hidden bg-white">
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
          <h3 className="text-sm font-semibold text-gray-700">Chat with AI</h3>
          <span className="text-[10px] text-gray-400">
            Ask about your contexts or use tools
          </span>
        </div>
        <ChatMessageList />
        <ChatInput onSend={handleSend} />
      </div>
    </div>
  );
}
