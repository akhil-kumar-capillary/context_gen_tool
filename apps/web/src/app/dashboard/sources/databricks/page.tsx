"use client";

import { useDatabricksStore } from "@/stores/databricks-store";
import { useDatabricksWebSocket } from "@/hooks/use-databricks-websocket";
import {
  PipelineStepper,
  ConnectionForm,
  ExtractionPanel,
  AnalysisPanel,
  DocGenerationPanel,
  RunDetailView,
} from "@/components/sources/databricks";

export default function DatabricksPage() {
  const { activeStep } = useDatabricksStore();

  // Connect to WebSocket for progress events
  useDatabricksWebSocket();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Databricks Source</h1>
        <p className="text-sm text-gray-500">
          Extract SQL from Databricks notebooks, analyze patterns, and generate context documents.
        </p>
      </div>

      {/* Pipeline stepper */}
      <PipelineStepper />

      {/* Active step content */}
      <div className="space-y-4">
        {activeStep === "connect" && <ConnectionForm />}
        {activeStep === "extract" && <ExtractionPanel />}
        {activeStep === "analyze" && <AnalysisPanel />}
        {activeStep === "generate" && <DocGenerationPanel />}
      </div>

      {/* Detail view (shows data from active runs) */}
      <RunDetailView />
    </div>
  );
}
