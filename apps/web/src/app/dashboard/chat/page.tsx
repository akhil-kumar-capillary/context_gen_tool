"use client";

import { useCallback } from "react";
import { useAuthStore } from "@/stores/auth-store";
import { useChatStore } from "@/stores/chat-store";
import { ConversationSidebar } from "@/components/chat/conversation-sidebar";
import { ChatPanel } from "@/components/chat/chat-panel";

export default function ChatPage() {
  const { token, orgId } = useAuthStore();
  const { setActiveConversation, setMessages } = useChatStore();

  const handleSelectConversation = useCallback(
    async (id: string) => {
      setActiveConversation(id);
      // Load messages for this conversation
      try {
        const resp = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/chat/conversations/${id}`,
          {
            headers: { Authorization: `Bearer ${token}` },
          }
        );
        if (resp.ok) {
          const data = await resp.json();
          setMessages(
            data.messages.map(
              (m: Record<string, unknown>) => ({
                id: m.id as string,
                conversationId: m.conversation_id as string,
                role: m.role as string,
                content: m.content as string,
                toolCalls: (m.tool_calls as Array<Record<string, unknown>> || []).map(
                  (tc) => ({
                    name: tc.name as string,
                    id: tc.id as string,
                    status: "done" as const,
                    summary: tc.result
                      ? String(tc.result).slice(0, 100)
                      : undefined,
                  })
                ),
                tokenUsage: m.token_usage as Record<string, number> | undefined,
                createdAt: m.created_at as string,
              })
            )
          );
        }
      } catch (err) {
        console.error("Failed to load conversation:", err);
      }
    },
    [token, setActiveConversation, setMessages]
  );

  return (
    <div className="-m-6 flex h-[calc(100vh-3.5rem)] overflow-hidden">
      <ConversationSidebar onSelectConversation={handleSelectConversation} />
      <ChatPanel />
    </div>
  );
}
