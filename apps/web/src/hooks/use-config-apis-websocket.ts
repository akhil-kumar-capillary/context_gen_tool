"use client";

import { useEffect, useRef, useCallback } from "react";
import { useAuthStore } from "@/stores/auth-store";
import { useConfigApisStore, type ProgressEvent } from "@/stores/config-apis-store";

/**
 * WebSocket hook for Config APIs pipeline progress events.
 *
 * Routes config_extraction_progress, config_analysis_progress,
 * config_generation_progress + completion/failure events to the store.
 */
export function useConfigApisWebSocket() {
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
  } = useConfigApisStore();

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
        if (channel === "config_extraction" || data.type === "config_extraction_progress") {
          addExtractionProgress(data);
        } else if (channel === "config_analysis" || data.type === "config_analysis_progress") {
          addAnalysisProgress(data);
        } else if (channel === "config_generation" || data.type === "config_generation_progress") {
          addGenerationProgress(data);
        }

        // Handle completion/failure events
        switch (data.type) {
          case "config_extraction_complete": {
            setIsExtracting(false);
            const extResult = (data as ProgressEvent & { result?: Record<string, unknown> }).result;
            addExtractionProgress({
              type: "config_extraction_progress",
              phase: "complete",
              status: "done",
              detail: "Extraction complete",
              ...(extResult || {}),
            });
            break;
          }
          case "config_extraction_failed":
            setIsExtracting(false);
            addExtractionProgress({
              type: "config_extraction_progress",
              phase: "error",
              status: "failed",
              error: data.error as string,
            });
            break;
          case "config_extraction_cancelled":
            setIsExtracting(false);
            addExtractionProgress({
              type: "config_extraction_progress",
              phase: "cancelled",
              status: "cancelled",
              detail: "Cancelled by user",
            });
            break;

          case "config_analysis_complete": {
            setIsAnalyzing(false);
            const analysisResult = (data as ProgressEvent & { result?: Record<string, unknown> }).result;
            if (analysisResult?.analysis_id) {
              setActiveAnalysisId(analysisResult.analysis_id as string);
            }
            addAnalysisProgress({
              type: "config_analysis_progress",
              phase: "complete",
              status: "done",
              detail: "Analysis complete",
            });
            break;
          }
          case "config_analysis_failed":
            setIsAnalyzing(false);
            addAnalysisProgress({
              type: "config_analysis_progress",
              phase: "error",
              status: "failed",
              error: data.error as string,
            });
            break;
          case "config_analysis_cancelled":
            setIsAnalyzing(false);
            addAnalysisProgress({
              type: "config_analysis_progress",
              phase: "cancelled",
              status: "cancelled",
              detail: "Cancelled by user",
            });
            break;

          case "config_generation_complete":
            setIsGenerating(false);
            addGenerationProgress({
              type: "config_generation_progress",
              phase: "complete",
              status: "done",
              detail: "Document generation complete",
            });
            break;
          case "config_generation_failed":
            setIsGenerating(false);
            addGenerationProgress({
              type: "config_generation_progress",
              phase: "error",
              status: "failed",
              error: data.error as string,
            });
            break;
          case "config_generation_cancelled":
            setIsGenerating(false);
            addGenerationProgress({
              type: "config_generation_progress",
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
