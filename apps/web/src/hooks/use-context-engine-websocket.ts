"use client";

import { useCallback } from "react";
import { useContextEngineStore } from "@/stores/context-engine-store";
import { useAuthStore } from "@/stores/auth-store";
import { apiClient } from "@/lib/api-client";
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
          // Guard: ignore if already completed (backend race condition)
          if (!useContextEngineStore.getState().isGenerating) break;
          setIsGenerating(false);
          addProgress({
            phase: "error",
            detail: (data.error as string) || "Generation failed",
            status: "failed",
          });
          break;

        case "context_engine_cancelled":
          if (!useContextEngineStore.getState().isGenerating) break;
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

  // On reconnect, reconcile state with backend
  const onReconnect = useCallback(() => {
    const { isGenerating } = useContextEngineStore.getState();
    if (!isGenerating) return;
    const { token, orgId } = useAuthStore.getState();
    if (!token || !orgId) return;
    // Check if the run we're tracking is still actually running
    apiClient
      .get<{ runs: Array<{ status: string }> }>(
        `/api/context-engine/runs?org_id=${orgId}`,
        { token },
      )
      .then((data) => {
        const running = data.runs.find((r) => r.status === "running");
        if (!running) {
          // No running run — clear stale isGenerating
          useContextEngineStore.getState().setIsGenerating(false);
        }
      })
      .catch(() => {});
  }, []);

  // On auth failure, clear all in-progress state
  const onAuthFailure = useCallback(() => {
    useContextEngineStore.getState().setIsGenerating(false);
  }, []);

  const { isConnected } = useWebSocket({
    endpoint: "/api/ws",
    onMessage,
    onReconnect,
    onAuthFailure,
  });

  return { isConnected };
}
