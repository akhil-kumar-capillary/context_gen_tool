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
    <div className="flex items-center gap-2">
      {STEPS.map((step, i) => {
        const Icon = step.icon;
        const isActive = step.id === activeStep;
        const isCompleted = i < stepIndex;

        return (
          <div key={step.id} className="flex items-center gap-2">
            {i > 0 && (
              <div
                className={cn(
                  "h-px w-8",
                  isCompleted ? "bg-violet-400" : "bg-gray-200"
                )}
              />
            )}
            <button
              onClick={() => !isRunning && setActiveStep(step.id)}
              disabled={isRunning}
              className={cn(
                "flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-violet-100 text-violet-700"
                  : isCompleted
                  ? "bg-green-50 text-green-700 hover:bg-green-100"
                  : "bg-gray-100 text-gray-500 hover:bg-gray-200",
                isRunning && "cursor-not-allowed opacity-60"
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
