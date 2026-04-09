"use client";

import { useCallback } from "react";
import { useDatabricksStore, type ProgressEvent } from "@/stores/databricks-store";
import { useWebSocket } from "./use-websocket";

/**
 * WebSocket hook for Databricks pipeline progress events.
 *
 * Listens for extraction_progress, analysis_progress, llm_progress,
 * and completion/failure events — routes them to the Databricks store.
 */
export function useDatabricksWebSocket() {
  const {
    addExtractionProgress,
    addAnalysisProgress,
    addGenerationProgress,
    setIsExtracting,
    setIsAnalyzing,
    setIsGenerating,
    setActiveAnalysisId,
  } = useDatabricksStore();

  const onMessage = useCallback(
    (data: Record<string, unknown>) => {
      const event = data as unknown as ProgressEvent;
      const channel = event.channel || event.type || "";

      // Route progress events to the correct store slice
      if (channel === "extraction" || data.type === "extraction_progress") {
        addExtractionProgress(event);
      } else if (channel === "analysis" || data.type === "analysis_progress") {
        addAnalysisProgress(event);
      } else if (channel === "llm" || data.type === "llm_progress") {
        addGenerationProgress(event);
      }

      // Handle completion/failure events
      switch (data.type) {
        case "extraction_complete": {
          setIsExtracting(false);
          const extResult = (data as Record<string, unknown>).result as Record<string, unknown> | undefined;
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
          if (!useDatabricksStore.getState().isExtracting) break;
          setIsExtracting(false);
          addExtractionProgress({
            type: "extraction_progress",
            phase: "error",
            status: "failed",
            error: data.error as string,
          });
          break;
        case "extraction_cancelled":
          if (!useDatabricksStore.getState().isExtracting) break;
          setIsExtracting(false);
          addExtractionProgress({
            type: "extraction_progress",
            phase: "cancelled",
            status: "cancelled",
            detail: "Cancelled by user",
          });
          break;

        case "analysis_complete": {
          setIsAnalyzing(false);
          const analysisResult = (data as Record<string, unknown>).result as Record<string, unknown> | undefined;
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
          if (!useDatabricksStore.getState().isAnalyzing) break;
          setIsAnalyzing(false);
          addAnalysisProgress({
            type: "analysis_progress",
            phase: "error",
            status: "failed",
            error: data.error as string,
          });
          break;
        case "analysis_cancelled":
          if (!useDatabricksStore.getState().isAnalyzing) break;
          setIsAnalyzing(false);
          addAnalysisProgress({
            type: "analysis_progress",
            phase: "cancelled",
            status: "cancelled",
            detail: "Cancelled by user",
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
          if (!useDatabricksStore.getState().isGenerating) break;
          setIsGenerating(false);
          addGenerationProgress({
            type: "llm_progress",
            phase: "error",
            status: "failed",
            error: data.error as string,
          });
          break;
        case "generation_cancelled":
          if (!useDatabricksStore.getState().isGenerating) break;
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
