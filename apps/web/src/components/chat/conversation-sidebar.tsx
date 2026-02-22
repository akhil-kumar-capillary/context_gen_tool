"use client";

import { useEffect } from "react";
import { MessageSquarePlus, MessageSquare, Trash2, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/stores/chat-store";
import { useAuthStore } from "@/stores/auth-store";
import type { ChatConversation } from "@/types";

interface ConversationSidebarProps {
  onSelectConversation: (id: string) => void;
}

export function ConversationSidebar({
  onSelectConversation,
}: ConversationSidebarProps) {
  const { token, orgId } = useAuthStore();
  const {
    conversations,
    activeConversationId,
    setConversations,
    setActiveConversation,
    removeConversation,
    newConversation,
  } = useChatStore();

  // Fetch conversations on mount
  useEffect(() => {
    if (!token || !orgId) return;

    const fetchConversations = async () => {
      try {
        const resp = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/chat/conversations?org_id=${orgId}`,
          {
            headers: { Authorization: `Bearer ${token}` },
          }
        );
        if (resp.ok) {
          const data = await resp.json();
          setConversations(
            data.map((c: Record<string, string | number>) => ({
              id: c.id,
              title: c.title,
              provider: c.provider,
              model: c.model,
              createdAt: c.created_at,
              updatedAt: c.updated_at,
              messageCount: c.message_count,
            }))
          );
        }
      } catch (err) {
        console.error("Failed to fetch conversations:", err);
      }
    };

    fetchConversations();
  }, [token, orgId, setConversations]);

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/chat/conversations/${id}`,
        {
          method: "DELETE",
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (resp.ok) {
        removeConversation(id);
      }
    } catch (err) {
      console.error("Failed to delete conversation:", err);
    }
  };

  const handleNew = () => {
    newConversation();
  };

  const handleSelect = (id: string) => {
    setActiveConversation(id);
    onSelectConversation(id);
  };

  // Group conversations by date
  const today = new Date().toDateString();
  const yesterday = new Date(Date.now() - 86400000).toDateString();

  const grouped: { label: string; items: ChatConversation[] }[] = [];
  const todayItems: ChatConversation[] = [];
  const yesterdayItems: ChatConversation[] = [];
  const olderItems: ChatConversation[] = [];

  for (const conv of conversations) {
    const date = new Date(conv.updatedAt).toDateString();
    if (date === today) todayItems.push(conv);
    else if (date === yesterday) yesterdayItems.push(conv);
    else olderItems.push(conv);
  }

  if (todayItems.length) grouped.push({ label: "Today", items: todayItems });
  if (yesterdayItems.length) grouped.push({ label: "Yesterday", items: yesterdayItems });
  if (olderItems.length) grouped.push({ label: "Previous", items: olderItems });

  return (
    <div className="flex h-full w-64 flex-col border-r border-gray-200 bg-gray-50">
      {/* New chat button */}
      <div className="p-3">
        <button
          onClick={handleNew}
          className="flex w-full items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50"
        >
          <MessageSquarePlus className="h-4 w-4" />
          New Chat
        </button>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto px-2 pb-3">
        {grouped.map((group) => (
          <div key={group.label} className="mb-3">
            <p className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-wider text-gray-400">
              {group.label}
            </p>
            {group.items.map((conv) => (
              <button
                key={conv.id}
                onClick={() => handleSelect(conv.id)}
                className={cn(
                  "group flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm transition-colors",
                  activeConversationId === conv.id
                    ? "bg-violet-100 text-violet-800"
                    : "text-gray-600 hover:bg-gray-100"
                )}
              >
                <MessageSquare className="h-3.5 w-3.5 shrink-0 opacity-50" />
                <span className="flex-1 truncate">{conv.title}</span>
                <button
                  onClick={(e) => handleDelete(conv.id, e)}
                  className="hidden shrink-0 rounded p-0.5 text-gray-400 hover:bg-red-100 hover:text-red-600 group-hover:block"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </button>
            ))}
          </div>
        ))}

        {conversations.length === 0 && (
          <p className="px-3 py-8 text-center text-xs text-gray-400">
            No conversations yet
          </p>
        )}
      </div>
    </div>
  );
}
