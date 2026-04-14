"use client";

import { useEffect, useCallback } from "react";
import { Loader2, Trash2, RefreshCw, CheckCircle, XCircle, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import { useDatabricksStore, type ExtractionRun } from "@/stores/databricks-store";

const STATUS_ICONS: Record<string, React.ReactNode> = {
  completed: <CheckCircle className="h-4 w-4 text-green-500" />,
  running: <Loader2 className="h-4 w-4 animate-spin text-primary" />,
  failed: <XCircle className="h-4 w-4 text-red-500" />,
};

export function ExtractionHistory() {
  const { token } = useAuthStore();
  const {
    extractionRuns,
    setExtractionRuns,
    isLoadingRuns,
    setIsLoadingRuns,
    setActiveExtractionId,
    setActiveStep,
  } = useDatabricksStore();

  const loadRuns = useCallback(async () => {
    setIsLoadingRuns(true);
    try {
      const data = await apiClient.get<{ runs: ExtractionRun[] }>(
        "/api/sources/databricks/extract/runs",
        { token: token || undefined }
      );
      setExtractionRuns(data.runs);
    } catch (err) {
      console.error("Failed to load runs:", err);
    } finally {
      setIsLoadingRuns(false);
    }
  }, [token, setExtractionRuns, setIsLoadingRuns]);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  const handleDelete = async (runId: string) => {
    if (!confirm("Delete this extraction run and all associated data?")) return;
    try {
      await apiClient.delete(`/api/sources/databricks/extract/runs/${runId}`, {
        token: token || undefined,
      });
      await loadRuns();
    } catch (err) {
      console.error("Failed to delete run:", err);
    }
  };

  const handleSelect = (runId: string) => {
    setActiveExtractionId(runId);
    setActiveStep("analyze");
  };

  if (isLoadingRuns) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!extractionRuns.length) return null;

  return (
    <div className="rounded-xl border border-border bg-background p-6">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground">Extraction History</h3>
        <button
          onClick={loadRuns}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-primary"
        >
          <RefreshCw className="h-3 w-3" />
          Refresh
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/50 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground">
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Instance</th>
              <th className="px-3 py-2">Notebooks</th>
              <th className="px-3 py-2">Valid SQLs</th>
              <th className="px-3 py-2">Started</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {extractionRuns.map((run) => (
              <tr
                key={run.id}
                className="border-b border-border last:border-0 hover:bg-muted/50"
              >
                <td className="px-3 py-2.5">
                  <span className="flex items-center gap-1.5">
                    {STATUS_ICONS[run.status] || <Clock className="h-4 w-4 text-muted-foreground" />}
                    <span className="text-xs">{run.status}</span>
                  </span>
                </td>
                <td className="py-2 font-mono text-xs text-muted-foreground">
                  {run.databricks_instance?.replace("https://", "").slice(0, 30)}
                </td>
                <td className="px-3 py-2.5">{run.total_notebooks ?? "-"}</td>
                <td className="px-3 py-2.5">{run.valid_sqls ?? "-"}</td>
                <td className="py-2 text-xs text-muted-foreground">
                  {run.started_at ? new Date(run.started_at).toLocaleString() : "-"}
                </td>
                <td className="px-3 py-2.5">
                  <div className="flex items-center gap-1">
                    {run.status === "completed" && (
                      <button
                        onClick={() => handleSelect(run.id)}
                        className="rounded-md px-2.5 py-1 text-xs font-medium text-primary hover:bg-primary/5"
                      >
                        Analyze
                      </button>
                    )}
                    <button
                      onClick={() => handleDelete(run.id)}
                      className="rounded p-1 text-muted-foreground hover:bg-red-50 hover:text-red-500"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
