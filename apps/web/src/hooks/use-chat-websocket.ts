"use client";

import { useRef, useCallback } from "react";
import { useAuthStore } from "@/stores/auth-store";
import { useChatStore } from "@/stores/chat-store";
import { useContextStore } from "@/stores/context-store";
import { useContextEngineStore } from "@/stores/context-engine-store";
import { useSettingsStore } from "@/stores/settings-store";
import { useWebSocket } from "./use-websocket";
import type { LLMUsage, AiGeneratedContext } from "@/types";

interface ChatWebSocketMessage {
  type: string;
  text?: string;
  tool?: string;
  tool_id?: string;
  display?: string;
  summary?: string;
  conversation_id?: string;
  usage?: LLMUsage;
  tool_calls?: Array<{ name: string; id: string }>;
  message?: string;
  // For ai_context_staged events
  context?: { name: string; content: string; scope: string };
  // For context_tree_updated events
  tree_data?: unknown;
  run_id?: string;
}

export function useChatWebSocket() {
  const cancelledRef = useRef(false);

  const { orgId } = useAuthStore();
  const { provider, model } = useSettingsStore();
  const {
    startStreaming,
    appendChunk,
    addToolCall,
    updateToolCallStatus,
    completeToolCall,
    finishStreaming,
    addMessage,
  } = useChatStore();

  const onMessage = useCallback(
    (raw: Record<string, unknown>) => {
      const data = raw as unknown as ChatWebSocketMessage;

      switch (data.type) {
        case "chat_chunk":
          if (data.text && !cancelledRef.current) {
            appendChunk(data.text);
          }
          break;

        case "tool_preparing":
          addToolCall({
            name: data.tool || "",
            id: data.tool_id || crypto.randomUUID(),
            status: "preparing",
            display: data.display,
          });
          break;

        case "tool_start": {
          const toolId = data.tool_id || crypto.randomUUID();
          const { activeToolCalls } = useChatStore.getState();
          const existing = activeToolCalls.find((tc) => tc.id === toolId);
          if (existing) {
            updateToolCallStatus(toolId, "running", data.display);
          } else {
            addToolCall({
              name: data.tool || "",
              id: toolId,
              status: "running",
              display: data.display,
            });
          }
          break;
        }

        case "tool_end":
          completeToolCall(data.tool_id || "", data.summary || "Done");
          break;

        case "chat_end": {
          cancelledRef.current = false;
          const { activeToolCalls: currentCalls } = useChatStore.getState();
          const mergedCalls =
            currentCalls.length > 0
              ? currentCalls.map((tc) => ({ ...tc, status: "done" as const }))
              : data.tool_calls?.map((tc) => ({
                  name: tc.name,
                  id: tc.id,
                  status: "done" as const,
                }));
          finishStreaming(
            data.conversation_id || "",
            data.usage,
            mergedCalls,
          );
          break;
        }

        case "error":
          finishStreaming(
            "",
            undefined,
            undefined,
            data.message || "An unknown error occurred",
          );
          break;

        case "ai_context_staged":
          if (data.context) {
            const { setAiContexts, aiContexts: currentAi } =
              useContextStore.getState();
            const newCtx: AiGeneratedContext = {
              id: crypto.randomUUID(),
              name: data.context.name,
              content: data.context.content,
              scope: (data.context.scope as "org" | "private") || "org",
              uploadStatus: "pending",
            };
            setAiContexts([...(currentAi || []), newCtx]);
          }
          break;

        case "trigger_bulk_upload":
          useContextStore.getState().bulkUpload();
          break;

        case "context_tree_updated":
          if (data.tree_data) {
            useContextEngineStore
              .getState()
              .setTreeData(data.tree_data as never);
          }
          break;

        case "auth_ok":
        case "pong":
          break;
      }
    },
    [
      appendChunk,
      addToolCall,
      updateToolCallStatus,
      completeToolCall,
      finishStreaming,
    ],
  );

  const { send, isConnected } = useWebSocket({
    endpoint: "/api/chat/ws/chat",
    onMessage,
  });

  // Send chat message
  const sendMessage = useCallback(
    (
      content: string,
      conversationId?: string | null,
      currentModule?: string | null,
    ) => {
      if (!isConnected) {
        addMessage({
          id: crypto.randomUUID(),
          conversationId: conversationId || "",
          role: "user",
          content,
          createdAt: new Date().toISOString(),
        });
        startStreaming();
        finishStreaming(
          "",
          undefined,
          undefined,
          "Not connected to server. Please check that the backend is running and refresh the page.",
        );
        return;
      }

      // Reset cancel state for new message
      cancelledRef.current = false;

      // Add user message to store immediately
      addMessage({
        id: crypto.randomUUID(),
        conversationId: conversationId || "",
        role: "user",
        content,
        createdAt: new Date().toISOString(),
      });

      // Start streaming state
      startStreaming();

      // Send to server
      send({
        type: "chat_message",
        content,
        conversation_id: conversationId,
        provider,
        model,
        org_id: orgId,
        current_module: currentModule || undefined,
      });
    },
    [isConnected, provider, model, orgId, addMessage, startStreaming, finishStreaming, send],
  );

  // Cancel current chat/tool execution
  const cancelChat = useCallback(() => {
    cancelledRef.current = true;
    send({ type: "cancel" });
    // Safety timeout in case backend doesn't respond with chat_end
    setTimeout(() => {
      const { isStreaming: stillStreaming } = useChatStore.getState();
      if (stillStreaming) {
        finishStreaming("", undefined, undefined, "Cancelled by user");
      }
    }, 3000);
  }, [send, finishStreaming]);

  return { sendMessage, cancelChat, isConnected };
}
