"use client";

import { useEffect, useCallback, useState } from "react";
import { Loader2, Play, BarChart3, ChevronRight, XCircle, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import {
  useDatabricksStore,
  type OrgIdEntry,
  type AnalysisRun,
} from "@/stores/databricks-store";

export function AnalysisPanel() {
  const { token, orgId: currentOrgId } = useAuthStore();
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
    activeAnalysisId,
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
        // Auto-select: always prefer the user's current org, fall back to first
        if (data.org_ids.length > 0) {
          const currentMatch = currentOrgId
            ? data.org_ids.find((o) => o.org_id === String(currentOrgId))
            : null;
          setSelectedOrgId(
            currentMatch ? currentMatch.org_id : data.org_ids[0].org_id
          );
        }
      } catch (err) {
        console.error("Failed to load org IDs:", err);
      } finally {
        setIsLoadingOrgs(false);
      }
    };

    loadOrgs();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeExtractionId, token, currentOrgId, setOrgIds, setSelectedOrgId]);

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

  const handleCancelAnalysis = useCallback(async () => {
    if (!activeExtractionId || !selectedOrgId) return;
    try {
      await apiClient.post(
        `/api/sources/databricks/analysis/cancel/${activeExtractionId}/${selectedOrgId}`,
        {},
        { token: token || undefined }
      );
    } catch {
      // Backend will also send ws event; just reset UI
    }
    setIsAnalyzing(false);
  }, [activeExtractionId, selectedOrgId, token, setIsAnalyzing]);

  const handleDeleteAnalysis = async (analysisId: string) => {
    if (!confirm("Delete this analysis run and all associated data?")) return;
    try {
      await apiClient.delete(`/api/sources/databricks/analysis/${analysisId}?org_id=${currentOrgId}`, {
        token: token || undefined,
      });
      // Remove from local state
      setAnalysisRuns(analysisRuns.filter((r) => r.id !== analysisId));
      // Clear active if this was the selected one
      if (activeAnalysisId === analysisId) {
        setActiveAnalysisId(null);
      }
    } catch (err) {
      console.error("Failed to delete analysis run:", err);
    }
  };

  const lastProgress = analysisProgress[analysisProgress.length - 1];
  const isComplete = lastProgress?.phase === "complete" || lastProgress?.status === "done";

  // When analysis completes, reload history so the new run appears
  // and fallback-set activeAnalysisId if the WS handler didn't capture it
  useEffect(() => {
    if (!isComplete || !activeExtractionId) return;

    const reloadHistory = async () => {
      try {
        const data = await apiClient.get<{ runs: AnalysisRun[] }>(
          `/api/sources/databricks/analysis/history/${activeExtractionId}`,
          { token: token || undefined }
        );
        setAnalysisRuns(data.runs);

        // If WS didn't set activeAnalysisId, pick the most recent run
        if (!activeAnalysisId && data.runs.length > 0) {
          setActiveAnalysisId(data.runs[0].id);
        }
      } catch (err) {
        console.error("Failed to reload analysis history:", err);
      }
    };

    reloadHistory();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isComplete, activeExtractionId, token]);

  const handleViewDashboard = (analysisId: string) => {
    setActiveAnalysisId(analysisId);
    // Stay on "analyze" step — RunDetailView will render the dashboard below
  };

  const handleSelectAnalysis = (analysisId: string) => {
    setActiveAnalysisId(analysisId);
    setActiveStep("generate");
  };

  const handleContinueToGenerate = () => {
    // If activeAnalysisId is already set (from WS or fallback), just navigate
    if (activeAnalysisId) {
      setActiveStep("generate");
      return;
    }
    // Last resort: pick the most recent analysis run from history
    if (analysisRuns.length > 0) {
      setActiveAnalysisId(analysisRuns[0].id);
      setActiveStep("generate");
    }
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-border bg-background p-6">
        <div className="mb-4 flex items-center gap-2">
          <BarChart3 className="h-5 w-5 text-primary" />
          <h2 className="text-lg font-semibold text-foreground">Analyze SQL Patterns</h2>
        </div>

        {!activeExtractionId ? (
          <p className="text-sm text-muted-foreground">
            Select an extraction run first, or go back to the extraction step.
          </p>
        ) : (
          <div className="space-y-4">
            {/* Org ID selector */}
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">
                Organization ID
              </label>
              {isLoadingOrgs ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading org IDs...
                </div>
              ) : orgIds.length === 0 ? (
                <p className="text-sm text-muted-foreground">No org IDs found in extracted SQLs.</p>
              ) : (
                <select
                  value={selectedOrgId || ""}
                  onChange={(e) => setSelectedOrgId(e.target.value)}
                  disabled={isAnalyzing}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 disabled:opacity-50"
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
                    ? "bg-muted text-muted-foreground"
                    : "bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm"
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
              {isAnalyzing && (
                <button
                  onClick={handleCancelAnalysis}
                  className="flex items-center gap-1.5 rounded-lg bg-[#eb6c6c] px-3 py-2 text-sm font-medium text-white shadow-sm transition-all hover:bg-[#d95b5b]"
                >
                  <XCircle className="h-4 w-4" />
                  Cancel
                </button>
              )}

              {lastProgress && (
                <span className="text-sm text-muted-foreground">
                  {lastProgress.detail || lastProgress.phase || ""}
                </span>
              )}
            </div>

            {/* Progress log */}
            {analysisProgress.length > 0 && (
              <div className="max-h-40 overflow-y-auto rounded-lg bg-muted/50 p-3">
                {analysisProgress.slice(-10).map((evt, i) => (
                  <div key={i} className="text-xs text-muted-foreground">
                    <span className="font-mono text-muted-foreground">[{evt.phase}]</span>{" "}
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
                onClick={handleContinueToGenerate}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:bg-primary/90"
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
        <div className="rounded-xl border border-border bg-background p-6">
          <h3 className="mb-3 text-sm font-semibold text-foreground">Analysis History</h3>
          <div className="space-y-2">
            {analysisRuns.map((run) => {
              const isActive = activeAnalysisId === run.id;
              return (
                <div
                  key={run.id}
                  onClick={() => handleViewDashboard(run.id)}
                  className={cn(
                    "flex items-center justify-between rounded-lg border p-3 cursor-pointer transition-all",
                    isActive
                      ? "border-primary/30 bg-primary/5 ring-1 ring-primary/20"
                      : "border-border hover:bg-muted/50"
                  )}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <BarChart3 className={cn(
                      "h-4 w-4 flex-shrink-0",
                      isActive ? "text-primary" : "text-muted-foreground"
                    )} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-foreground">
                          org={run.org_id} v{run.version}
                        </span>
                        {isActive && (
                          <span className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">
                            Viewing
                          </span>
                        )}
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {run.fingerprint_count ?? 0} fingerprints · {run.notebook_count ?? 0} notebooks
                        {run.created_at && (
                          <> · {new Date(run.created_at).toLocaleDateString()}</>
                        )}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleSelectAnalysis(run.id);
                      }}
                      className="rounded-md px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/10 transition-colors"
                    >
                      Generate Docs
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteAnalysis(run.id);
                      }}
                      className="rounded p-1 text-muted-foreground hover:bg-red-50 hover:text-red-500 transition-colors"
                      title="Delete analysis run"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                    <ChevronRight className={cn(
                      "h-4 w-4 transition-transform",
                      isActive ? "text-primary rotate-90" : "text-muted-foreground"
                    )} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
