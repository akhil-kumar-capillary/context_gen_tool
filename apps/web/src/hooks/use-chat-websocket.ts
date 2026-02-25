"use client";

import { useEffect, useRef, useCallback } from "react";
import { useAuthStore } from "@/stores/auth-store";
import { useChatStore } from "@/stores/chat-store";
import { useContextStore } from "@/stores/context-store";
import { useSettingsStore } from "@/stores/settings-store";
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
}

export function useChatWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout>>();
  const reconnectAttempts = useRef(0);
  const cancelledRef = useRef(false);

  const { token, orgId } = useAuthStore();
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

  // Connect WebSocket
  const connect = useCallback(() => {
    if (!token) return;

    const wsBase = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";
    const url = `${wsBase}/api/chat/ws/chat?token=${token}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectAttempts.current = 0;
    };

    ws.onmessage = (event) => {
      try {
        const data: ChatWebSocketMessage = JSON.parse(event.data);

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
            const mergedCalls = currentCalls.length > 0
              ? currentCalls.map((tc) => ({ ...tc, status: "done" as const }))
              : data.tool_calls?.map((tc) => ({
                  name: tc.name,
                  id: tc.id,
                  status: "done" as const,
                }));
            finishStreaming(
              data.conversation_id || "",
              data.usage,
              mergedCalls
            );
            break;
          }

          case "error":
            finishStreaming("", undefined, undefined, data.message || "An unknown error occurred");
            break;

          case "ai_context_staged":
            if (data.context) {
              const { setAiContexts, aiContexts: currentAi } = useContextStore.getState();
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

          case "pong":
            break;
        }
      } catch {
        // Ignore non-JSON messages
      }
    };

    ws.onclose = () => {
      wsRef.current = null;
      if (reconnectAttempts.current < 5) {
        reconnectAttempts.current++;
        const delay = Math.min(1000 * 2 ** reconnectAttempts.current, 30000);
        reconnectRef.current = setTimeout(connect, delay);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [token, appendChunk, addToolCall, updateToolCallStatus, completeToolCall, finishStreaming]);

  // Auto-connect on mount
  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnect on unmount
        wsRef.current.close();
      }
    };
  }, [connect]);

  // Send chat message
  const sendMessage = useCallback(
    (content: string, conversationId?: string | null) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
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
          "Not connected to server. Please check that the backend is running and refresh the page."
        );
        return;
      }

      // Reset cancel state for new message
      cancelledRef.current = false;

      // Add user message to store immediately
      const userMessage = {
        id: crypto.randomUUID(),
        conversationId: conversationId || "",
        role: "user" as const,
        content,
        createdAt: new Date().toISOString(),
      };
      addMessage(userMessage);

      // Start streaming state
      startStreaming();

      // Send to server
      wsRef.current.send(
        JSON.stringify({
          type: "chat_message",
          content,
          conversation_id: conversationId,
          provider,
          model,
          org_id: orgId,
        })
      );
    },
    [provider, model, orgId, addMessage, startStreaming, finishStreaming]
  );

  // Cancel current chat/tool execution
  const cancelChat = useCallback(() => {
    cancelledRef.current = true;
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "cancel" }));
    }
    // Safety timeout in case backend doesn't respond with chat_end
    setTimeout(() => {
      const { isStreaming: stillStreaming } = useChatStore.getState();
      if (stillStreaming) {
        finishStreaming("", undefined, undefined, "Cancelled by user");
      }
    }, 3000);
  }, [finishStreaming]);

  const isConnected = wsRef.current?.readyState === WebSocket.OPEN;

  return { sendMessage, cancelChat, isConnected };
}
