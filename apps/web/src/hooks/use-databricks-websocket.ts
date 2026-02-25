"use client";

import { useEffect, useRef, useCallback } from "react";
import { useAuthStore } from "@/stores/auth-store";
import { useDatabricksStore, type ProgressEvent } from "@/stores/databricks-store";

/**
 * WebSocket hook for Databricks pipeline progress events.
 *
 * Listens for extraction_progress, analysis_progress, llm_progress,
 * and completion/failure events — routes them to the Databricks store.
 *
 * Uses the same WS connection pattern as use-chat-websocket.ts.
 */
export function useDatabricksWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout>>();
  const reconnectAttempts = useRef(0);

  const { token } = useAuthStore();
  const {
    addExtractionProgress,
    addAnalysisProgress,
    addGenerationProgress,
    setIsExtracting,
    setIsAnalyzing,
    setIsGenerating,
    setActiveAnalysisId,
  } = useDatabricksStore();

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
        const data: ProgressEvent = JSON.parse(event.data);
        const channel = data.channel || data.type || "";

        // Route progress events to the correct store slice
        if (channel === "extraction" || data.type === "extraction_progress") {
          addExtractionProgress(data);
        } else if (channel === "analysis" || data.type === "analysis_progress") {
          addAnalysisProgress(data);
        } else if (channel === "llm" || data.type === "llm_progress") {
          addGenerationProgress(data);
        }

        // Handle completion/failure events
        switch (data.type) {
          case "extraction_complete": {
            setIsExtracting(false);
            // Merge summary stats from result into the progress event
            // so the extraction panel can display stat cards
            const extResult = (data as ProgressEvent & { result?: Record<string, unknown> }).result;
            const extSummary = extResult?.summary as Record<string, unknown> | undefined;
            addExtractionProgress({
              type: "extraction_progress",
              phase: "complete",
              status: "done",
              detail: "Extraction complete",
              ...(extSummary || extResult || {}),
            });
            break;
          }
          case "extraction_failed":
            setIsExtracting(false);
            addExtractionProgress({
              type: "extraction_progress",
              phase: "error",
              status: "failed",
              error: data.error as string,
            });
            break;
          case "analysis_complete": {
            setIsAnalyzing(false);
            const analysisResult = (data as ProgressEvent & { result?: Record<string, unknown> }).result;
            if (analysisResult?.analysis_id) {
              setActiveAnalysisId(analysisResult.analysis_id as string);
            }
            addAnalysisProgress({
              type: "analysis_progress",
              phase: "complete",
              status: "done",
              detail: "Analysis complete",
            });
            break;
          }
          case "analysis_failed":
            setIsAnalyzing(false);
            addAnalysisProgress({
              type: "analysis_progress",
              phase: "error",
              status: "failed",
              error: data.error as string,
            });
            break;
          case "generation_complete":
            setIsGenerating(false);
            addGenerationProgress({
              type: "llm_progress",
              phase: "complete",
              status: "done",
              detail: "Document generation complete",
            });
            break;
          case "generation_failed":
            setIsGenerating(false);
            addGenerationProgress({
              type: "llm_progress",
              phase: "error",
              status: "failed",
              error: data.error as string,
            });
            break;
          case "extraction_cancelled":
            setIsExtracting(false);
            addExtractionProgress({
              type: "extraction_progress",
              phase: "cancelled",
              status: "cancelled",
              detail: "Cancelled by user",
            });
            break;
          case "analysis_cancelled":
            setIsAnalyzing(false);
            addAnalysisProgress({
              type: "analysis_progress",
              phase: "cancelled",
              status: "cancelled",
              detail: "Cancelled by user",
            });
            break;
          case "generation_cancelled":
            setIsGenerating(false);
            addGenerationProgress({
              type: "llm_progress",
              phase: "cancelled",
              status: "cancelled",
              detail: "Cancelled by user",
            });
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
  }, [
    token,
    addExtractionProgress,
    addAnalysisProgress,
    addGenerationProgress,
    setIsExtracting,
    setIsAnalyzing,
    setIsGenerating,
    setActiveAnalysisId,
  ]);

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

  const isConnected = wsRef.current?.readyState === WebSocket.OPEN;

  return { isConnected };
}
