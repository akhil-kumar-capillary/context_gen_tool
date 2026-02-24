"use client";

import { useState, useCallback, useMemo } from "react";
import {
  Loader2,
  Play,
  FolderSearch,
  ChevronRight,
  FileText,
  Download,
  Code2,
  Briefcase,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import { useDatabricksStore } from "@/stores/databricks-store";
import { ExtractionHistory } from "./extraction-history";

// Phase config — matches the Electron reference app
const PHASE_CONFIG: Record<
  string,
  { label: string; icon: React.ElementType; color: string }
> = {
  discovery: { label: "Discovering notebooks", icon: FolderSearch, color: "text-blue-500" },
  metadata: { label: "Fetching metadata", icon: FileText, color: "text-indigo-500" },
  export: { label: "Exporting notebooks", icon: Download, color: "text-purple-500" },
  extraction: { label: "Extracting SQL", icon: Code2, color: "text-emerald-500" },
  jobs: { label: "Fetching job history", icon: Briefcase, color: "text-amber-500" },
  complete: { label: "Complete", icon: CheckCircle2, color: "text-green-500" },
};

export function ExtractionPanel() {
  const { token } = useAuthStore();
  const {
    isExtracting,
    extractionProgress,
    setIsExtracting,
    clearExtractionProgress,
    setActiveExtractionId,
    setActiveStep,
  } = useDatabricksStore();

  const [rootPath, setRootPath] = useState("/Workspace");
  const [modifiedSince, setModifiedSince] = useState("");
  const [maxWorkers, setMaxWorkers] = useState(10);

  const handleStart = useCallback(async () => {
    if (isExtracting) return;
    setIsExtracting(true);
    clearExtractionProgress();

    try {
      const result = await apiClient.post<{ run_id: string; status: string }>(
        "/api/sources/databricks/extract/start",
        {
          root_path: rootPath,
          modified_since: modifiedSince || null,
          max_workers: maxWorkers,
        },
        { token: token || undefined }
      );
      setActiveExtractionId(result.run_id);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Extraction failed";
      setIsExtracting(false);
      console.error("Extraction start failed:", msg);
    }
  }, [
    isExtracting, rootPath, modifiedSince, maxWorkers, token,
    setIsExtracting, clearExtractionProgress, setActiveExtractionId,
  ]);

  // Derive latest progress state
  const lastProgress = extractionProgress[extractionProgress.length - 1];
  const isComplete = lastProgress?.phase === "complete" || lastProgress?.status === "done";
  const hasError = extractionProgress.some((e) => e.error);

  // Find the latest event per phase (for summary stats)
  const latestByPhase = useMemo(() => {
    const map: Record<string, typeof lastProgress> = {};
    for (const evt of extractionProgress) {
      if (evt.phase) map[evt.phase] = evt;
    }
    return map;
  }, [extractionProgress]);

  // Current phase info
  const currentPhase = lastProgress?.phase || "discovery";
  const phaseConfig = PHASE_CONFIG[currentPhase] || PHASE_CONFIG.discovery;
  const PhaseIcon = phaseConfig.icon;
  const completed = lastProgress?.completed ?? 0;
  const total = lastProgress?.total ?? 0;
  const pct = total > 0 ? Math.min(Math.round((completed / total) * 100), 100) : 0;
  const hasFailures = lastProgress?.detail?.includes("failure") ?? false;

  // Extract summary stats from the "complete" progress event
  const summaryStats = useMemo(() => {
    if (!isComplete) return null;
    const completeEvt = latestByPhase["complete"];
    const extractionEvt = latestByPhase["extraction"];
    return {
      totalNotebooks: (completeEvt?.total_notebooks as number) ?? (extractionEvt?.total as number) ?? 0,
      processedNotebooks: (completeEvt?.processed_notebooks as number) ?? (extractionEvt?.completed as number) ?? 0,
      validSqls: (completeEvt?.valid_sqls as number) ?? 0,
      totalSqls: (completeEvt?.total_cells as number) ?? (completeEvt?.total_sqls as number) ?? 0,
      uniqueHashes: (completeEvt?.unique_hashes as number) ?? 0,
      apiFailures: (completeEvt?.api_failures as number) ?? 0,
    };
  }, [isComplete, latestByPhase]);

  return (
    <div className="space-y-4">
      {/* ── Config form ── */}
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <div className="mb-4 flex items-center gap-2">
          <FolderSearch className="h-5 w-5 text-violet-600" />
          <h2 className="text-lg font-semibold text-gray-900">Extract Notebooks</h2>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Root Path
            </label>
            <input
              type="text"
              value={rootPath}
              onChange={(e) => setRootPath(e.target.value)}
              placeholder="/Workspace"
              disabled={isExtracting}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-100 disabled:opacity-50"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Modified Since (optional)
            </label>
            <input
              type="date"
              value={modifiedSince}
              onChange={(e) => setModifiedSince(e.target.value)}
              disabled={isExtracting}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-100 disabled:opacity-50"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Concurrency
            </label>
            <input
              type="number"
              value={maxWorkers}
              onChange={(e) => setMaxWorkers(Number(e.target.value))}
              min={1}
              max={50}
              disabled={isExtracting}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-100 disabled:opacity-50"
            />
          </div>
        </div>

        <div className="mt-4">
          <button
            onClick={handleStart}
            disabled={isExtracting}
            className={cn(
              "flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all",
              isExtracting
                ? "bg-gray-100 text-gray-400"
                : "bg-violet-600 text-white hover:bg-violet-700 shadow-sm"
            )}
          >
            {isExtracting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Extracting...
              </>
            ) : (
              <>
                <Play className="h-4 w-4" />
                Start Extraction
              </>
            )}
          </button>
        </div>
      </div>

      {/* ── Live Progress Panel ── */}
      {isExtracting && lastProgress && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-3">
          {/* Phase header */}
          <div className="flex items-center justify-between">
            <div className={cn("flex items-center gap-2", phaseConfig.color)}>
              <PhaseIcon className="h-4 w-4" />
              <span className="text-sm font-medium">{phaseConfig.label}</span>
            </div>
            <div className="flex items-center gap-3">
              {hasFailures && (
                <span className="flex items-center gap-1 text-xs font-medium text-amber-500">
                  <AlertTriangle className="h-3 w-3" />
                  API failures detected
                </span>
              )}
              {total > 0 && (
                <span className="text-xs tabular-nums text-gray-500">
                  {completed.toLocaleString()}/{total.toLocaleString()}
                </span>
              )}
            </div>
          </div>

          {/* Progress bar */}
          {total > 0 && (
            <div className="h-2 overflow-hidden rounded-full bg-gray-100">
              <div
                className="h-full rounded-full bg-violet-500 transition-all duration-300"
                style={{ width: `${pct}%` }}
              />
            </div>
          )}

          {/* Detail text */}
          {lastProgress.detail && (
            <p className={cn("text-xs", hasFailures ? "text-amber-500" : "text-gray-500")}>
              {lastProgress.detail}
            </p>
          )}
        </div>
      )}

      {/* ── Extraction Error ── */}
      {hasError && !isExtracting && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4">
          <div className="flex items-center gap-2 text-red-600">
            <AlertTriangle className="h-4 w-4" />
            <span className="text-sm font-medium">Extraction Failed</span>
          </div>
          <p className="mt-1 text-xs text-red-500">
            {extractionProgress.find((e) => e.error)?.error || "Unknown error"}
          </p>
        </div>
      )}

      {/* ── Summary (on complete) ── */}
      {isComplete && summaryStats && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-3">
          <div className="flex items-center gap-2 text-green-500">
            <CheckCircle2 className="h-4 w-4" />
            <span className="text-sm font-medium">Extraction Complete</span>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <StatCard label="Total Notebooks" value={summaryStats.totalNotebooks} />
            <StatCard label="Processed" value={summaryStats.processedNotebooks} />
            <StatCard label="Valid SQLs" value={summaryStats.validSqls} />
            <StatCard label="Total SQL Cells" value={summaryStats.totalSqls} />
            <StatCard label="Unique Queries" value={summaryStats.uniqueHashes} />
            {summaryStats.apiFailures > 0 && (
              <StatCard label="API Failures" value={summaryStats.apiFailures} warn />
            )}
          </div>

          {summaryStats.apiFailures > 0 && (
            <div className="flex items-center gap-2 text-xs text-amber-500">
              <AlertTriangle className="h-3 w-3" />
              {summaryStats.apiFailures} API failures — some notebooks may not have been fully processed
            </div>
          )}

          <button
            onClick={() => setActiveStep("analyze")}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-violet-600 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:bg-violet-700"
          >
            Continue to Analysis
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}

      <ExtractionHistory />
    </div>
  );
}

function StatCard({ label, value, warn }: { label: string; value: number; warn?: boolean }) {
  return (
    <div className={cn("rounded-lg px-3 py-2.5", warn ? "bg-amber-50" : "bg-gray-50")}>
      <p className={cn("text-lg font-semibold tabular-nums", warn ? "text-amber-600" : "text-gray-900")}>
        {value.toLocaleString()}
      </p>
      <p className="text-xs text-gray-500">{label}</p>
    </div>
  );
}
