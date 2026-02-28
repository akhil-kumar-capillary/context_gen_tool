"use client";

import { useEffect } from "react";
import {
  Loader2, Play, Square, ChevronRight, Check, AlertCircle, Clock, Trash2,
} from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import {
  useConfigApisStore,
  type AnalysisRun,
} from "@/stores/config-apis-store";
import { AnalysisDashboard } from "./analysis-dashboard";

export function AnalysisPanel() {
  const { token } = useAuthStore();
  const {
    activeExtractionId,
    extractionRuns,
    analysisRuns,
    activeAnalysisId,
    analysisProgress,
    isAnalyzing,
    isLoadingAnalysis,
    setAnalysisRuns,
    setActiveAnalysisId,
    setIsAnalyzing,
    clearAnalysisProgress,
    setActiveStep,
    setIsLoadingAnalysis,
    setEntityTypeCounts,
    setClusters,
    setCounters,
  } = useConfigApisStore();

  // Get the active extraction
  const activeExtraction = extractionRuns.find((r) => r.id === activeExtractionId);

  // Load analysis history for the active extraction
  useEffect(() => {
    if (!token || !activeExtractionId) return;
    const load = async () => {
      setIsLoadingAnalysis(true);
      try {
        const data = await apiClient.get<{ runs: AnalysisRun[] }>(
          `/api/sources/config-apis/analysis/history/${activeExtractionId}`,
          { token }
        );
        setAnalysisRuns(data.runs);
      } catch (e) {
        console.error("Failed to load analysis history:", e);
      }
      setIsLoadingAnalysis(false);
    };
    load();
  }, [token, activeExtractionId, setAnalysisRuns, setIsLoadingAnalysis]);

  const handleStart = async () => {
    if (!token || !activeExtractionId) return;

    clearAnalysisProgress();
    setIsAnalyzing(true);

    try {
      const data = await apiClient.post<{ analysis_id: string }>(
        "/api/sources/config-apis/analysis/start",
        { run_id: activeExtractionId },
        { token }
      );
      setActiveAnalysisId(data.analysis_id);
    } catch (e) {
      console.error("Analysis failed to start:", e);
      setIsAnalyzing(false);
    }
  };

  const handleCancel = async () => {
    if (!token || !activeAnalysisId) return;
    try {
      await apiClient.post(
        `/api/sources/config-apis/analysis/cancel/${activeAnalysisId}`,
        {},
        { token }
      );
    } catch {
      // ignore
    }
  };

  const handleDeleteAnalysis = async (analysisId: string) => {
    if (!confirm("Delete this analysis run and all associated data?")) return;
    try {
      await apiClient.delete(`/api/sources/config-apis/analysis/${analysisId}`, {
        token: token || undefined,
      });
      setAnalysisRuns(analysisRuns.filter((r) => r.id !== analysisId));
      if (activeAnalysisId === analysisId) {
        setActiveAnalysisId(null);
      }
    } catch (err) {
      console.error("Failed to delete analysis run:", err);
    }
  };

  const isComplete = analysisProgress.some(
    (p) => p.phase === "complete" && p.status === "done"
  );

  // Reload history on completion and set the active analysis ID
  useEffect(() => {
    if (!isComplete || !activeExtractionId || !token) return;
    const reload = async () => {
      try {
        const data = await apiClient.get<{ runs: AnalysisRun[] }>(
          `/api/sources/config-apis/analysis/history/${activeExtractionId}`,
          { token }
        );
        setAnalysisRuns(data.runs);
        if (!activeAnalysisId && data.runs.length > 0) {
          setActiveAnalysisId(data.runs[0].id);
        }
      } catch {
        // ignore
      }
    };
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isComplete, activeExtractionId, token]);

  // Load dashboard data (clusters, counters, entity type counts) for AnalysisDashboard
  useEffect(() => {
    if (!token || !activeAnalysisId) return;
    const loadDashboard = async () => {
      try {
        const [clustersData, countersData] = await Promise.all([
          apiClient.get<{ clusters: unknown[] }>(
            `/api/sources/config-apis/review/clusters/${activeAnalysisId}`,
            { token }
          ),
          apiClient.get<{ counters: Record<string, unknown>; entity_type_counts: Record<string, number> }>(
            `/api/sources/config-apis/review/counters/${activeAnalysisId}`,
            { token }
          ),
        ]);
        setClusters(clustersData.clusters as never);
        setCounters(countersData.counters);
        setEntityTypeCounts(countersData.entity_type_counts);
      } catch {
        // Dashboard data is optional — don't block on errors
      }
    };
    loadDashboard();
  }, [token, activeAnalysisId, setClusters, setCounters, setEntityTypeCounts]);

  if (!activeExtractionId) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white px-6 py-12 text-center">
        <p className="text-sm text-gray-400">
          Select an extraction run first, or go back to the extraction step.
        </p>
        <button
          onClick={() => setActiveStep("extract")}
          className="mt-3 text-sm text-violet-600 hover:text-violet-700"
        >
          Go to Extraction
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Extraction summary */}
      {activeExtraction && (
        <div className="rounded-xl border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">
            Extraction: {activeExtraction.categories?.length} categories
          </h3>
          <div className="flex flex-wrap gap-4 text-xs text-gray-500">
            <span>Host: {activeExtraction.host}</span>
            <span>Status: {activeExtraction.status}</span>
            <span>Date: {formatDate(activeExtraction.created_at || null)}</span>
          </div>
          {activeExtraction.stats && (
            <div className="mt-3 flex flex-wrap gap-2">
              {Object.entries(activeExtraction.stats).map(([cat, stat]) => (
                <span
                  key={cat}
                  className={cn(
                    "rounded-full px-2.5 py-1 text-[11px] font-medium",
                    stat.failed > 0
                      ? "bg-yellow-50 text-yellow-700"
                      : "bg-green-50 text-green-700"
                  )}
                >
                  {cat}: {stat.success}/{stat.apis}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex items-center gap-3">
        {!isAnalyzing ? (
          <button
            onClick={handleStart}
            disabled={activeExtraction?.status !== "completed"}
            className="flex items-center gap-2 rounded-lg bg-violet-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-50"
          >
            <Play className="h-4 w-4" />
            Start Analysis
          </button>
        ) : (
          <button
            onClick={handleCancel}
            className="flex items-center gap-2 rounded-lg bg-red-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-red-700"
          >
            <Square className="h-4 w-4" />
            Stop
          </button>
        )}

        {(isComplete || activeAnalysisId) && (
          <button
            onClick={() => setActiveStep("review")}
            className="flex items-center gap-2 rounded-lg border border-violet-300 bg-violet-50 px-5 py-2.5 text-sm font-medium text-violet-700 hover:bg-violet-100"
          >
            Continue to Review
            <ChevronRight className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Progress log */}
      {analysisProgress.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white">
          <div className="border-b border-gray-200 px-5 py-3">
            <h3 className="text-sm font-semibold text-gray-700">
              Analysis Progress
              {isAnalyzing && <Loader2 className="ml-2 inline h-3.5 w-3.5 animate-spin" />}
            </h3>
          </div>
          <div className="max-h-64 overflow-y-auto p-4">
            {analysisProgress.map((p, i) => (
              <div
                key={i}
                className={cn(
                  "flex items-start gap-2 py-1 text-xs",
                  p.status === "failed" ? "text-red-600" : p.phase === "complete" ? "text-green-600" : "text-gray-600"
                )}
              >
                {p.status === "done" || p.phase === "complete" ? (
                  <Check className="mt-0.5 h-3 w-3 shrink-0 text-green-500" />
                ) : p.status === "failed" ? (
                  <AlertCircle className="mt-0.5 h-3 w-3 shrink-0 text-red-500" />
                ) : (
                  <Clock className="mt-0.5 h-3 w-3 shrink-0 text-gray-400" />
                )}
                <span>{p.detail || p.error || p.phase || "..."}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Analysis Dashboard — shown after analysis completes */}
      {(isComplete || activeAnalysisId) && <AnalysisDashboard />}

      {/* Analysis History */}
      {analysisRuns.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white">
          <div className="border-b border-gray-200 px-5 py-3">
            <h3 className="text-sm font-semibold text-gray-700">Analysis History</h3>
          </div>
          <div className="divide-y divide-gray-50">
            {analysisRuns.map((run) => (
              <div
                key={run.id}
                onClick={() => {
                  setActiveAnalysisId(run.id);
                  setActiveStep("review");
                }}
                className={cn(
                  "flex w-full items-center justify-between px-5 py-3 text-left hover:bg-gray-50 transition-colors cursor-pointer",
                  activeAnalysisId === run.id && "bg-violet-50"
                )}
              >
                <div>
                  <span className="text-xs font-medium text-gray-900">
                    v{run.version}
                  </span>
                  <span
                    className={cn(
                      "ml-2 rounded-full px-2 py-0.5 text-[10px] font-medium",
                      run.status === "completed"
                        ? "bg-green-100 text-green-700"
                        : "bg-red-100 text-red-700"
                    )}
                  >
                    {run.status}
                  </span>
                  <p className="text-[11px] text-gray-400 mt-0.5">
                    {formatDate(run.created_at || null)}
                  </p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteAnalysis(run.id);
                    }}
                    className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-500 transition-colors"
                    title="Delete analysis run"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                  <ChevronRight className="h-4 w-4 text-gray-300" />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
