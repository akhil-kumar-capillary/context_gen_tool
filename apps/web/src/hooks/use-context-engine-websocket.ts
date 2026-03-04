"use client";

import { useCallback } from "react";
import { useContextEngineStore } from "@/stores/context-engine-store";
import { useWebSocket } from "./use-websocket";

/**
 * WebSocket hook for Context Engine progress events.
 *
 * Routes context_engine_progress, context_engine_complete,
 * context_engine_failed, and context_engine_cancelled events to the store.
 */
export function useContextEngineWebSocket() {
  const { addProgress, setIsGenerating, setActiveRunId } =
    useContextEngineStore();

  const onMessage = useCallback(
    (data: Record<string, unknown>) => {
      switch (data.type) {
        case "context_engine_progress":
          addProgress({
            phase: (data.phase as string) || "",
            detail: (data.detail as string) || "",
            status: (data.status as string) || "running",
          });
          break;

        case "context_engine_complete":
          setIsGenerating(false);
          addProgress({
            phase: "complete",
            detail: `Tree generated with ${data.input_context_count || 0} contexts`,
            status: "done",
          });
          if (data.run_id) {
            setActiveRunId(data.run_id as string);
          }
          break;

        case "context_engine_failed":
          setIsGenerating(false);
          addProgress({
            phase: "error",
            detail: (data.error as string) || "Generation failed",
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
          if (data.tree_data) {
            useContextEngineStore.getState().setTreeData(data.tree_data as never);
          }
          break;

        case "pong":
          break;
      }
    },
    [addProgress, setIsGenerating, setActiveRunId],
  );

  const { isConnected } = useWebSocket({
    endpoint: "/api/ws",
    onMessage,
  });

  return { isConnected };
}
