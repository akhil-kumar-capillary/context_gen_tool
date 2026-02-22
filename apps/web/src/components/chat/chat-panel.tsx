"use client";

import { useCallback } from "react";
import { useChatStore } from "@/stores/chat-store";
import { useChatWebSocket } from "@/hooks/use-chat-websocket";
import { ChatMessageList } from "./chat-message-list";
import { ChatInput } from "./chat-input";

export function ChatPanel() {
  const { activeConversationId } = useChatStore();
  const { sendMessage } = useChatWebSocket();

  const handleSend = useCallback(
    (content: string) => {
      sendMessage(content, activeConversationId);
    },
    [sendMessage, activeConversationId]
  );

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <ChatMessageList />
      <ChatInput onSend={handleSend} />
    </div>
  );
}
