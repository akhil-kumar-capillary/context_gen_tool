"use client";

import { useEffect, useCallback, useState } from "react";
import { Loader2, Play, BarChart3, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import {
  useDatabricksStore,
  type OrgIdEntry,
  type AnalysisRun,
} from "@/stores/databricks-store";

export function AnalysisPanel() {
  const { token } = useAuthStore();
  const {
    activeExtractionId,
    orgIds,
    setOrgIds,
    selectedOrgId,
    setSelectedOrgId,
    isAnalyzing,
    setIsAnalyzing,
    analysisProgress,
    clearAnalysisProgress,
    setActiveAnalysisId,
    analysisRuns,
    setAnalysisRuns,
    setActiveStep,
    isLoadingAnalysis,
    setIsLoadingAnalysis,
  } = useDatabricksStore();

  const [isLoadingOrgs, setIsLoadingOrgs] = useState(false);

  // Load org IDs when extraction ID changes
  useEffect(() => {
    if (!activeExtractionId) return;

    const loadOrgs = async () => {
      setIsLoadingOrgs(true);
      try {
        const data = await apiClient.get<{ org_ids: OrgIdEntry[] }>(
          `/api/sources/databricks/analysis/org-ids/${activeExtractionId}`,
          { token: token || undefined }
        );
        setOrgIds(data.org_ids);
        // Auto-select first org
        if (data.org_ids.length > 0 && !selectedOrgId) {
          setSelectedOrgId(data.org_ids[0].org_id);
        }
      } catch (err) {
        console.error("Failed to load org IDs:", err);
      } finally {
        setIsLoadingOrgs(false);
      }
    };

    loadOrgs();
  }, [activeExtractionId, token, setOrgIds, setSelectedOrgId, selectedOrgId]);

  // Load analysis history
  useEffect(() => {
    if (!activeExtractionId) return;

    const loadHistory = async () => {
      setIsLoadingAnalysis(true);
      try {
        const data = await apiClient.get<{ runs: AnalysisRun[] }>(
          `/api/sources/databricks/analysis/history/${activeExtractionId}`,
          { token: token || undefined }
        );
        setAnalysisRuns(data.runs);
      } catch (err) {
        console.error("Failed to load analysis history:", err);
      } finally {
        setIsLoadingAnalysis(false);
      }
    };

    loadHistory();
  }, [activeExtractionId, token, setAnalysisRuns, setIsLoadingAnalysis]);

  const handleStartAnalysis = useCallback(async () => {
    if (!activeExtractionId || !selectedOrgId || isAnalyzing) return;

    setIsAnalyzing(true);
    clearAnalysisProgress();

    try {
      await apiClient.post(
        "/api/sources/databricks/analysis/start",
        { run_id: activeExtractionId, org_id: selectedOrgId },
        { token: token || undefined }
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Analysis failed to start";
      setIsAnalyzing(false);
      console.error("Analysis start failed:", msg);
    }
  }, [
    activeExtractionId, selectedOrgId, isAnalyzing, token,
    setIsAnalyzing, clearAnalysisProgress,
  ]);

  const lastProgress = analysisProgress[analysisProgress.length - 1];
  const isComplete = lastProgress?.phase === "complete" || lastProgress?.status === "done";

  const handleSelectAnalysis = (analysisId: string) => {
    setActiveAnalysisId(analysisId);
    setActiveStep("generate");
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <div className="mb-4 flex items-center gap-2">
          <BarChart3 className="h-5 w-5 text-violet-600" />
          <h2 className="text-lg font-semibold text-gray-900">Analyze SQL Patterns</h2>
        </div>

        {!activeExtractionId ? (
          <p className="text-sm text-gray-500">
            Select an extraction run first, or go back to the extraction step.
          </p>
        ) : (
          <div className="space-y-4">
            {/* Org ID selector */}
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Organization ID
              </label>
              {isLoadingOrgs ? (
                <div className="flex items-center gap-2 text-sm text-gray-400">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading org IDs...
                </div>
              ) : orgIds.length === 0 ? (
                <p className="text-sm text-gray-500">No org IDs found in extracted SQLs.</p>
              ) : (
                <select
                  value={selectedOrgId || ""}
                  onChange={(e) => setSelectedOrgId(e.target.value)}
                  disabled={isAnalyzing}
                  className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-100 disabled:opacity-50"
                >
                  {orgIds.map((org) => (
                    <option key={org.org_id} value={org.org_id}>
                      {org.org_id} ({org.valid_sqls} valid SQLs / {org.total_sqls} total)
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* Start button */}
            <div className="flex items-center gap-3">
              <button
                onClick={handleStartAnalysis}
                disabled={isAnalyzing || !selectedOrgId}
                className={cn(
                  "flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all",
                  isAnalyzing || !selectedOrgId
                    ? "bg-gray-100 text-gray-400"
                    : "bg-violet-600 text-white hover:bg-violet-700 shadow-sm"
                )}
              >
                {isAnalyzing ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Analyzing...
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4" />
                    Start Analysis
                  </>
                )}
              </button>

              {lastProgress && (
                <span className="text-sm text-gray-500">
                  {lastProgress.detail || lastProgress.phase || ""}
                </span>
              )}
            </div>

            {/* Progress log */}
            {analysisProgress.length > 0 && (
              <div className="max-h-40 overflow-y-auto rounded-lg bg-gray-50 p-3">
                {analysisProgress.slice(-10).map((evt, i) => (
                  <div key={i} className="text-xs text-gray-600">
                    <span className="font-mono text-gray-400">[{evt.phase}]</span>{" "}
                    {evt.detail || evt.status || ""}
                    {evt.error && (
                      <span className="text-red-500"> {evt.error}</span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {isComplete && (
              <button
                onClick={() => setActiveStep("generate")}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-violet-600 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:bg-violet-700"
              >
                Continue to Doc Generation
                <ChevronRight className="h-4 w-4" />
              </button>
            )}
          </div>
        )}
      </div>

      {/* Analysis history */}
      {analysisRuns.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h3 className="mb-3 text-sm font-semibold text-gray-900">Analysis History</h3>
          <div className="space-y-2">
            {analysisRuns.map((run) => (
              <div
                key={run.id}
                className="flex items-center justify-between rounded-lg border border-gray-200 p-3 hover:bg-gray-50"
              >
                <div>
                  <span className="text-sm font-medium text-gray-900">
                    org={run.org_id} v{run.version}
                  </span>
                  <span className="ml-2 text-xs text-gray-500">
                    {run.fingerprint_count ?? 0} fingerprints, {run.notebook_count ?? 0} notebooks
                  </span>
                </div>
                <button
                  onClick={() => handleSelectAnalysis(run.id)}
                  className="rounded-md px-3 py-1.5 text-xs font-medium text-violet-600 hover:bg-violet-50"
                >
                  Generate Docs
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
