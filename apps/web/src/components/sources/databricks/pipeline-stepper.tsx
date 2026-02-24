"use client";

import { Link, FolderSearch, BarChart3, Sparkles, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDatabricksStore, type PipelineStep } from "@/stores/databricks-store";

const STEPS: { id: PipelineStep; label: string; icon: React.ReactNode }[] = [
  { id: "connect", label: "Connect", icon: <Link className="h-4 w-4" /> },
  { id: "extract", label: "Extract", icon: <FolderSearch className="h-4 w-4" /> },
  { id: "analyze", label: "Analyze", icon: <BarChart3 className="h-4 w-4" /> },
  { id: "generate", label: "Generate", icon: <Sparkles className="h-4 w-4" /> },
];

const STEP_ORDER: PipelineStep[] = ["connect", "extract", "analyze", "generate"];

export function PipelineStepper() {
  const { activeStep, setActiveStep, connectionStatus, activeExtractionId, activeAnalysisId } =
    useDatabricksStore();

  const activeIdx = STEP_ORDER.indexOf(activeStep);

  const canNavigate = (step: PipelineStep): boolean => {
    switch (step) {
      case "connect":
        return true;
      case "extract":
        return connectionStatus === "connected";
      case "analyze":
        return !!activeExtractionId;
      case "generate":
        return !!activeAnalysisId;
      default:
        return false;
    }
  };

  const isCompleted = (step: PipelineStep): boolean => {
    const stepIdx = STEP_ORDER.indexOf(step);
    return stepIdx < activeIdx;
  };

  return (
    <div className="flex items-center gap-2">
      {STEPS.map((step, i) => {
        const active = step.id === activeStep;
        const completed = isCompleted(step.id);
        const enabled = canNavigate(step.id);

        return (
          <div key={step.id} className="flex items-center">
            {i > 0 && (
              <div
                className={cn(
                  "mx-2 h-px w-8",
                  completed ? "bg-violet-400" : "bg-gray-200"
                )}
              />
            )}
            <button
              onClick={() => enabled && setActiveStep(step.id)}
              disabled={!enabled}
              className={cn(
                "flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition-all",
                active
                  ? "bg-violet-600 text-white shadow-sm"
                  : completed
                  ? "bg-violet-100 text-violet-700 hover:bg-violet-200"
                  : enabled
                  ? "bg-gray-100 text-gray-600 hover:bg-gray-200"
                  : "bg-gray-50 text-gray-400 cursor-not-allowed"
              )}
            >
              {completed ? <Check className="h-3.5 w-3.5" /> : step.icon}
              {step.label}
            </button>
          </div>
        );
      })}
    </div>
  );
}
