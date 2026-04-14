"use client";

import { useEffect, useRef } from "react";
import { useAuthStore } from "@/stores/auth-store";
import { useConfigApisStore } from "@/stores/config-apis-store";
import { useConfigApisWebSocket } from "@/hooks/use-config-apis-websocket";
import { ModuleGuard } from "@/components/layout/module-guard";
import {
  PipelineStepper,
  ExtractionPanel,
  AnalysisPanel,
  ReviewPanel,
  DocGenerationPanel,
} from "@/components/sources/config-apis";

export default function ConfigApisPage() {
  const { orgId } = useAuthStore();
  const { activeStep } = useConfigApisStore();

  // Reset store when org changes (skip hydration: null → number)
  const prevOrgIdRef = useRef(orgId);
  useEffect(() => {
    if (prevOrgIdRef.current !== orgId && prevOrgIdRef.current !== null && orgId !== null) {
      useConfigApisStore.getState().reset();
    }
    prevOrgIdRef.current = orgId;
  }, [orgId]);

  // Connect to WebSocket for progress events
  useConfigApisWebSocket();

  return (
    <ModuleGuard module="config_apis">
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-foreground">
            Configuration APIs Source
          </h1>
          <p className="text-sm text-muted-foreground">
            Extract Capillary platform configurations, analyze patterns, and
            generate context documents.
          </p>
        </div>

        {/* Pipeline stepper */}
        <PipelineStepper />

        {/* Active step content */}
        <div className="space-y-4">
          {activeStep === "extract" && <ExtractionPanel />}
          {activeStep === "analyze" && <AnalysisPanel />}
          {activeStep === "review" && <ReviewPanel />}
          {activeStep === "generate" && <DocGenerationPanel />}
        </div>
      </div>
    </ModuleGuard>
  );
}
