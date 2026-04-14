"use client";

import { useConfigApisStore, type PipelineStep } from "@/stores/config-apis-store";
import { Database, BarChart3, ListChecks, FileText, Check } from "lucide-react";
import { cn } from "@/lib/utils";

const STEPS: { id: PipelineStep; label: string; icon: typeof Database }[] = [
  { id: "extract", label: "Extract", icon: Database },
  { id: "analyze", label: "Analyze", icon: BarChart3 },
  { id: "review", label: "Review & Select", icon: ListChecks },
  { id: "generate", label: "Generate", icon: FileText },
];

export function PipelineStepper() {
  const {
    activeStep,
    setActiveStep,
    isExtracting,
    isAnalyzing,
    isGenerating,
    isLoadingReviewData,
  } = useConfigApisStore();

  const stepIndex = STEPS.findIndex((s) => s.id === activeStep);
  const isRunning = isExtracting || isAnalyzing || isGenerating || isLoadingReviewData;

  return (
    <div className="flex items-center gap-1">
      {STEPS.map((step, i) => {
        const Icon = step.icon;
        const isActive = step.id === activeStep;
        const isCompleted = i < stepIndex;
        const enabled = !isRunning;

        return (
          <div key={step.id} className="flex items-center">
            {i > 0 && (
              <div
                className={cn(
                  "mx-1.5 h-px w-6 transition-colors",
                  isCompleted ? "bg-primary" : "bg-border",
                )}
              />
            )}
            <button
              onClick={() => enabled && setActiveStep(step.id)}
              disabled={!enabled}
              className={cn(
                "flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all",
                isActive
                  ? "bg-primary text-primary-foreground shadow-sm ring-2 ring-primary/30"
                  : isCompleted
                    ? "bg-primary/10 text-primary hover:bg-primary/15"
                    : enabled
                      ? "bg-muted text-muted-foreground hover:bg-muted/80"
                      : "bg-muted/50 text-muted-foreground/50 cursor-not-allowed",
              )}
            >
              {isCompleted ? (
                <Check className="h-4 w-4" />
              ) : (
                <Icon className="h-4 w-4" />
              )}
              {step.label}
            </button>
          </div>
        );
      })}
    </div>
  );
}
