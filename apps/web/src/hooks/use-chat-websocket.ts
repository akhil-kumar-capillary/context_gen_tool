"use client";

import { useEffect, useRef, useCallback } from "react";
import { useAuthStore } from "@/stores/auth-store";
import { useChatStore } from "@/stores/chat-store";
import { useSettingsStore } from "@/stores/settings-store";
import type { LLMUsage } from "@/types";

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
}

export function useChatWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout>>();
  const reconnectAttempts = useRef(0);

  const { token, orgId } = useAuthStore();
  const { provider, model } = useSettingsStore();
  const {
    startStreaming,
    appendChunk,
    addToolCall,
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
            if (data.text) {
              appendChunk(data.text);
            }
            break;

          case "tool_start":
            addToolCall({
              name: data.tool || "",
              id: data.tool_id || crypto.randomUUID(),
              status: "running",
              display: data.display,
            });
            break;

          case "tool_end":
            completeToolCall(data.tool_id || "", data.summary || "Done");
            break;

          case "chat_end":
            finishStreaming(
              data.conversation_id || "",
              data.usage,
              data.tool_calls?.map((tc) => ({
                name: tc.name,
                id: tc.id,
                status: "done" as const,
              }))
            );
            break;

          case "error":
            // Stop streaming and show error
            finishStreaming("", undefined, undefined);
            console.error("Chat error:", data.message);
            break;

          case "pong":
            // Ignore pong
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
  }, [token, appendChunk, addToolCall, completeToolCall, finishStreaming]);

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
        console.error("WebSocket not connected");
        return;
      }

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
    [provider, model, orgId, addMessage, startStreaming]
  );

  const isConnected = wsRef.current?.readyState === WebSocket.OPEN;

  return { sendMessage, isConnected };
}
