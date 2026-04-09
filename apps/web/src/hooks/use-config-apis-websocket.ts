"use client";

import { useCallback } from "react";
import { useConfigApisStore, type ProgressEvent } from "@/stores/config-apis-store";
import { useWebSocket } from "./use-websocket";

/**
 * WebSocket hook for Config APIs pipeline progress events.
 *
 * Routes config_extraction_progress, config_analysis_progress,
 * config_generation_progress + completion/failure events to the store.
 */
export function useConfigApisWebSocket() {
  const {
    addExtractionProgress,
    addAnalysisProgress,
    addGenerationProgress,
    setIsExtracting,
    setIsAnalyzing,
    setIsGenerating,
    setActiveAnalysisId,
  } = useConfigApisStore();

  const onMessage = useCallback(
    (data: Record<string, unknown>) => {
      const event = data as unknown as ProgressEvent;
      const channel = event.channel || event.type || "";

      // Route progress events to the correct store slice
      if (channel === "config_extraction" || data.type === "config_extraction_progress") {
        addExtractionProgress(event);
      } else if (channel === "config_analysis" || data.type === "config_analysis_progress") {
        addAnalysisProgress(event);
      } else if (channel === "config_generation" || data.type === "config_generation_progress") {
        addGenerationProgress(event);
      }

      // Handle completion/failure events
      switch (data.type) {
        case "config_extraction_complete": {
          setIsExtracting(false);
          const extResult = (data as Record<string, unknown>).result as Record<string, unknown> | undefined;
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
          if (!useConfigApisStore.getState().isExtracting) break;
          setIsExtracting(false);
          addExtractionProgress({
            type: "config_extraction_progress",
            phase: "error",
            status: "failed",
            error: data.error as string,
          });
          break;
        case "config_extraction_cancelled":
          if (!useConfigApisStore.getState().isExtracting) break;
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
          const analysisResult = (data as Record<string, unknown>).result as Record<string, unknown> | undefined;
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
          if (!useConfigApisStore.getState().isAnalyzing) break;
          setIsAnalyzing(false);
          addAnalysisProgress({
            type: "config_analysis_progress",
            phase: "error",
            status: "failed",
            error: data.error as string,
          });
          break;
        case "config_analysis_cancelled":
          if (!useConfigApisStore.getState().isAnalyzing) break;
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
          if (!useConfigApisStore.getState().isGenerating) break;
          setIsGenerating(false);
          addGenerationProgress({
            type: "config_generation_progress",
            phase: "error",
            status: "failed",
            error: data.error as string,
          });
          break;
        case "config_generation_cancelled":
          if (!useConfigApisStore.getState().isGenerating) break;
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
    },
    [
      addExtractionProgress,
      addAnalysisProgress,
      addGenerationProgress,
      setIsExtracting,
      setIsAnalyzing,
      setIsGenerating,
      setActiveAnalysisId,
    ],
  );

  const { isConnected } = useWebSocket({
    endpoint: "/api/ws",
    onMessage,
  });

  return { isConnected };
}
