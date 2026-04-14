"use client";

import { Link, FolderSearch, BarChart3, Sparkles, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDatabricksStore, type PipelineStep } from "@/stores/databricks-store";

const STEPS: { id: PipelineStep; label: string; icon: React.ReactNode; num: number }[] = [
  { id: "connect", label: "Connect", icon: <Link className="h-4 w-4" />, num: 1 },
  { id: "extract", label: "Extract", icon: <FolderSearch className="h-4 w-4" />, num: 2 },
  { id: "analyze", label: "Analyze", icon: <BarChart3 className="h-4 w-4" />, num: 3 },
  { id: "generate", label: "Generate", icon: <Sparkles className="h-4 w-4" />, num: 4 },
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
    return STEP_ORDER.indexOf(step) < activeIdx;
  };

  return (
    <div className="flex items-center gap-1">
      {STEPS.map((step, i) => {
        const active = step.id === activeStep;
        const completed = isCompleted(step.id);
        const enabled = canNavigate(step.id);

        return (
          <div key={step.id} className="flex items-center">
            {i > 0 && (
              <div
                className={cn(
                  "mx-1.5 h-px w-6 transition-colors",
                  completed ? "bg-primary" : "bg-border",
                )}
              />
            )}
            <button
              onClick={() => enabled && setActiveStep(step.id)}
              disabled={!enabled}
              className={cn(
                "flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all",
                active
                  ? "bg-primary text-primary-foreground shadow-sm ring-2 ring-primary/30"
                  : completed
                    ? "bg-primary/10 text-primary hover:bg-primary/15"
                    : enabled
                      ? "bg-muted text-muted-foreground hover:bg-muted/80"
                      : "bg-muted/50 text-muted-foreground/50 cursor-not-allowed",
              )}
            >
              {completed ? (
                <Check className="h-4 w-4" />
              ) : (
                step.icon
              )}
              {step.label}
            </button>
          </div>
        );
      })}
    </div>
  );
}
