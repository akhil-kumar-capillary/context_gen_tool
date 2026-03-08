"use client";

import { useEffect, useRef } from "react";
import { useAuthStore } from "@/stores/auth-store";
import { useContextStore } from "@/stores/context-store";
import { useChatStore } from "@/stores/chat-store";
import { ContextPanel } from "@/components/contexts/context-panel";
import { ModuleGuard } from "@/components/layout/module-guard";

export default function ContextsPage() {
  const { orgId } = useAuthStore();
  const { queueMessage } = useChatStore();

  // Reset stores when org changes (skip hydration: null → number)
  const prevOrgIdRef = useRef(orgId);
  useEffect(() => {
    if (prevOrgIdRef.current !== orgId && prevOrgIdRef.current !== null && orgId !== null) {
      useContextStore.getState().reset();
      useChatStore.getState().reset();
    }
    prevOrgIdRef.current = orgId;
  }, [orgId]);

  return (
    <ModuleGuard module="context_management">
      <ContextPanel onSendChatMessage={queueMessage} />
    </ModuleGuard>
  );
}
