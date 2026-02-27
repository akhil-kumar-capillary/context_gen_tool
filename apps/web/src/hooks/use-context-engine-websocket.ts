"use client";

import { useEffect, useRef, useCallback } from "react";
import { useAuthStore } from "@/stores/auth-store";
import { useContextEngineStore } from "@/stores/context-engine-store";

/**
 * WebSocket hook for Context Engine progress events.
 *
 * Routes context_engine_progress, context_engine_complete,
 * context_engine_failed, and context_engine_cancelled events to the store.
 */
export function useContextEngineWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout>>();
  const reconnectAttempts = useRef(0);

  const { token } = useAuthStore();
  const { addProgress, setIsGenerating, setActiveRunId } =
    useContextEngineStore();

  const connect = useCallback(() => {
    if (!token) return;

    const wsBase = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";
    const url = `${wsBase}/api/ws?token=${token}`;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectAttempts.current = 0;
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        switch (data.type) {
          case "context_engine_progress":
            addProgress({
              phase: data.phase || "",
              detail: data.detail || "",
              status: data.status || "running",
            });
            break;

          case "context_engine_complete":
            setIsGenerating(false);
            addProgress({
              phase: "complete",
              detail: `Tree generated with ${data.input_context_count || 0} contexts`,
              status: "done",
            });
            // Set the active run ID so the UI loads the new tree
            if (data.run_id) {
              setActiveRunId(data.run_id);
            }
            break;

          case "context_engine_failed":
            setIsGenerating(false);
            addProgress({
              phase: "error",
              detail: data.error || "Generation failed",
              status: "failed",
            });
            break;

          case "context_engine_cancelled":
            setIsGenerating(false);
            addProgress({
              phase: "cancelled",
              detail: "Cancelled by user",
              status: "failed",
            });
            break;

          case "context_tree_updated":
            // Real-time tree updates from chat tools (Phase C)
            if (data.tree_data) {
              useContextEngineStore.getState().setTreeData(data.tree_data);
            }
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
  }, [token, addProgress, setIsGenerating, setActiveRunId]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect]);

  return { isConnected: wsRef.current?.readyState === WebSocket.OPEN };
}
