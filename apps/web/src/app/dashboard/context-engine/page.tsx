"use client";

import { useEffect, useCallback, useRef } from "react";
import {
  Loader2,
  Play,
  Square,
  Check,
  AlertCircle,
  Clock,
  Upload,
  RefreshCw,
  ChevronRight,
  GitBranch,
  Trash2,
} from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import {
  useContextEngineStore,
  type TreeRun,
} from "@/stores/context-engine-store";
import { useContextEngineWebSocket } from "@/hooks/use-context-engine-websocket";
import { TreeView, NodeDetail, SecretDetail } from "@/components/context-engine";
import { ModuleGuard } from "@/components/layout/module-guard";

export default function ContextEnginePage() {
  const { token, orgId } = useAuthStore();
  const {
    treeRuns,
    activeRunId,
    treeData,
    isGenerating,
    generationProgress,
    selectedNodeId,
    isLoadingRuns,
    isLoadingTree,
    isSyncing,
    syncResults,
    setTreeRuns,
    setActiveRunId,
    setTreeData,
    setIsGenerating,
    clearProgress,
    setIsLoadingRuns,
    setIsLoadingTree,
    setIsSyncing,
    setSyncResults,
    selectNode,
    setIsEditing,
  } = useContextEngineStore();

  // Reset context engine state when org changes
  const prevOrgIdRef = useRef(orgId);
  useEffect(() => {
    if (prevOrgIdRef.current !== orgId) {
      prevOrgIdRef.current = orgId;
      setTreeRuns([]);
      setActiveRunId(null);
      setTreeData(null);
      clearProgress();
      setSyncResults(null);
      selectNode(null);
      setIsEditing(false);
      setIsSyncing(false);
      setIsGenerating(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId]);

  // Connect WebSocket
  useContextEngineWebSocket();

  // Load tree runs on mount
  useEffect(() => {
    if (!token || !orgId) return;
    const load = async () => {
      setIsLoadingRuns(true);
      try {
        const data = await apiClient.get<{ runs: TreeRun[] }>(
          `/api/context-engine/runs?org_id=${orgId}`,
          { token }
        );
        setTreeRuns(data.runs);

        // Auto-select latest completed run if none active
        if (!activeRunId && data.runs.length > 0) {
          const latest = data.runs.find((r) => r.status === "completed");
          if (latest) {
            setActiveRunId(latest.id);
          }
        }
      } catch (e) {
        console.error("Failed to load tree runs:", e);
      }
      setIsLoadingRuns(false);
    };
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, orgId]);

  // Reusable tree loader
  const loadTreeData = useCallback(
    async (runId: string) => {
      if (!token) return;
      setIsLoadingTree(true);
      try {
        const data = await apiClient.get<{ tree_data: unknown }>(
          `/api/context-engine/runs/${runId}`,
          { token }
        );
        if (data.tree_data) {
          setTreeData(data.tree_data as never);
        }
      } catch (e) {
        console.error("Failed to load tree data:", e);
      }
      setIsLoadingTree(false);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [token]
  );

  // Load tree data when active run changes
  useEffect(() => {
    if (!activeRunId) {
      setTreeData(null);
      return;
    }
    loadTreeData(activeRunId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRunId, loadTreeData]);

  // Reload runs when generation completes
  const isComplete = generationProgress.some(
    (p) => p.phase === "complete" && p.status === "done"
  );

  useEffect(() => {
    if (!isComplete || !token || !orgId) return;
    const reload = async () => {
      try {
        // Reload the runs list
        const data = await apiClient.get<{ runs: TreeRun[] }>(
          `/api/context-engine/runs?org_id=${orgId}`,
          { token }
        );
        setTreeRuns(data.runs);

        // Also reload the tree data for the active run — the activeRunId
        // useEffect won't re-fire because the ID hasn't changed, so we
        // must fetch the tree explicitly here.
        if (activeRunId) {
          await loadTreeData(activeRunId);
        }
      } catch {
        // ignore
      }
      setIsGenerating(false);
    };
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isComplete, token, orgId]);

  // ── Handlers ──

  const handleGenerate = async () => {
    if (!token || !orgId) return;
    clearProgress();
    setIsGenerating(true);

    try {
      const data = await apiClient.post<{ run_id: string }>(
        `/api/context-engine/generate?org_id=${orgId}`,
        {},
        { token }
      );
      setActiveRunId(data.run_id);
    } catch (e) {
      console.error("Failed to start generation:", e);
      setIsGenerating(false);
    }
  };

  const handleCancel = async () => {
    if (!token || !activeRunId) return;
    try {
      await apiClient.post(
        `/api/context-engine/generate/cancel/${activeRunId}`,
        {},
        { token }
      );
    } catch {
      // ignore
    }
  };

  const handleSync = async () => {
    if (!token || !activeRunId || !orgId) return;
    setIsSyncing(true);
    setSyncResults(null);
    try {
      const data = await apiClient.post<{
        results: Array<{ name: string; status: string; reason?: string }>;
        uploaded: number;
        total: number;
      }>(`/api/context-engine/runs/${activeRunId}/sync?org_id=${orgId}`, {}, { token });
      setSyncResults(data.results);
    } catch (e) {
      console.error("Sync failed:", e);
    }
    setIsSyncing(false);
  };

  const handleDeleteRun = async (runId: string) => {
    if (!token) return;
    try {
      await apiClient.delete(`/api/context-engine/runs/${runId}`, { token });
      // Remove from local state
      setTreeRuns(treeRuns.filter((r) => r.id !== runId));
      // If we deleted the active run, clear the tree
      if (activeRunId === runId) {
        setActiveRunId(null);
        setTreeData(null);
      }
    } catch (e) {
      console.error("Failed to delete run:", e);
    }
  };

  // ── Render ──

  const showDetailPanel = selectedNodeId !== null;
  const showSecretPanel =
    selectedNodeId !== null && selectedNodeId.startsWith("secret:");

  return (
    <ModuleGuard module="context_engine">
    <div className="flex h-[calc(100vh-3.5rem)] -m-6 overflow-hidden">
      {/* Left panel: Controls + History */}
      <div className="w-72 flex-shrink-0 border-r border-gray-200 flex flex-col bg-white overflow-y-auto">
        {/* Header */}
        <div className="border-b border-gray-200 p-4">
          <div className="flex items-center gap-2 mb-1">
            <GitBranch className="h-5 w-5 text-violet-600" />
            <h1 className="text-lg font-bold text-gray-900">Context Engine</h1>
          </div>
          <p className="text-xs text-gray-500">
            Organize all contexts into an intelligent tree structure.
          </p>
        </div>

        {/* Generate button */}
        <div className="p-4 border-b border-gray-200">
          {!isGenerating ? (
            <button
              onClick={handleGenerate}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-violet-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-violet-700 transition-colors"
            >
              <Play className="h-4 w-4" />
              Generate Tree
            </button>
          ) : (
            <button
              onClick={handleCancel}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-red-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-red-700 transition-colors"
            >
              <Square className="h-4 w-4" />
              Stop
            </button>
          )}

          {/* Sync button */}
          {activeRunId && treeData && !isGenerating && (
            <button
              onClick={handleSync}
              disabled={isSyncing}
              className="mt-2 flex w-full items-center justify-center gap-2 rounded-lg border border-violet-300 bg-violet-50 px-4 py-2 text-sm font-medium text-violet-700 hover:bg-violet-100 transition-colors disabled:opacity-50"
            >
              {isSyncing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Upload className="h-4 w-4" />
              )}
              Sync to Capillary
            </button>
          )}
        </div>

        {/* Progress */}
        {generationProgress.length > 0 && (
          <div className="border-b border-gray-200 p-4">
            <h3 className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-2">
              Progress
              {isGenerating && (
                <Loader2 className="ml-1.5 inline h-3 w-3 animate-spin" />
              )}
            </h3>
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {generationProgress.map((p, i) => (
                <div
                  key={i}
                  className={cn(
                    "flex items-start gap-1.5 text-[11px]",
                    p.status === "failed"
                      ? "text-red-600"
                      : p.phase === "complete"
                        ? "text-green-600"
                        : "text-gray-600"
                  )}
                >
                  {p.status === "done" || p.phase === "complete" ? (
                    <Check className="mt-0.5 h-3 w-3 shrink-0 text-green-500" />
                  ) : p.status === "failed" ? (
                    <AlertCircle className="mt-0.5 h-3 w-3 shrink-0 text-red-500" />
                  ) : (
                    <Clock className="mt-0.5 h-3 w-3 shrink-0 text-gray-400" />
                  )}
                  <span className="break-words">{p.detail || p.phase}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Sync results */}
        {syncResults && (
          <div className="border-b border-gray-200 p-4">
            <h3 className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-2">
              Sync Results
            </h3>
            <div className="space-y-1 max-h-32 overflow-y-auto">
              {syncResults.map((r, i) => (
                <div key={i} className="flex items-center gap-1.5 text-[11px]">
                  {r.status === "uploaded" ? (
                    <Check className="h-3 w-3 text-green-500" />
                  ) : (
                    <AlertCircle className="h-3 w-3 text-red-500" />
                  )}
                  <span
                    className={
                      r.status === "uploaded"
                        ? "text-green-700"
                        : "text-red-600"
                    }
                  >
                    {r.name}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Run history */}
        <div className="flex-1 p-4">
          <h3 className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-2">
            History
          </h3>
          {isLoadingRuns ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
            </div>
          ) : treeRuns.length === 0 ? (
            <p className="text-xs text-gray-400">
              No tree runs yet. Click &quot;Generate Tree&quot; to get started.
            </p>
          ) : (
            <div className="space-y-1">
              {treeRuns.map((run) => (
                <div
                  key={run.id}
                  className={cn(
                    "group flex w-full items-center justify-between rounded-lg px-3 py-2 text-left transition-colors cursor-pointer",
                    activeRunId === run.id
                      ? "bg-violet-50 border border-violet-200"
                      : "hover:bg-gray-50 border border-transparent"
                  )}
                  onClick={() => {
                    if (activeRunId === run.id) {
                      loadTreeData(run.id);
                    } else {
                      setActiveRunId(run.id);
                    }
                  }}
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-[10px] font-medium",
                          run.status === "completed"
                            ? "bg-green-100 text-green-700"
                            : run.status === "running"
                              ? "bg-blue-100 text-blue-700"
                              : "bg-red-100 text-red-700"
                        )}
                      >
                        {run.status}
                      </span>
                      {run.input_context_count && (
                        <span className="text-[10px] text-gray-400">
                          {run.input_context_count} contexts
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-gray-400 mt-0.5">
                      {formatDate(run.created_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteRun(run.id);
                      }}
                      className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-red-50 text-gray-300 hover:text-red-500 transition-all"
                      title="Delete run"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                    <ChevronRight className="h-3.5 w-3.5 text-gray-300" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Center: Tree View */}
      <div className="flex-1 flex flex-col min-w-0">
        {isLoadingTree ? (
          <div className="flex items-center justify-center flex-1">
            <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
            <span className="ml-2 text-sm text-gray-400">Loading tree...</span>
          </div>
        ) : !treeData ? (
          <div className="flex flex-col items-center justify-center flex-1">
            <GitBranch className="h-12 w-12 text-gray-200 mb-3" />
            <p className="text-sm text-gray-400">
              {activeRunId
                ? "Tree data not available for this run."
                : "Generate a tree to visualize your contexts."}
            </p>
          </div>
        ) : (
          <div className="flex flex-1 min-h-0">
            {/* Tree */}
            <div
              className={cn(
                "border-r border-gray-200 bg-white overflow-hidden flex flex-col",
                showDetailPanel ? "w-1/2" : "w-full"
              )}
            >
              <TreeView />
            </div>

            {/* Detail panel */}
            {showDetailPanel && (
              <div className="w-1/2 bg-white overflow-hidden flex flex-col">
                {showSecretPanel ? <SecretDetail /> : <NodeDetail />}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
    </ModuleGuard>
  );
}
