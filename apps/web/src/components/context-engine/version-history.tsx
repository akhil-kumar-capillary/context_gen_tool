"use client";

import { useEffect, useState } from "react";
import {
  Loader2,
  History,
  RotateCcw,
  Trash2,
  ChevronDown,
  ChevronUp,
  Save,
  Layers,
} from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import {
  useContextEngineStore,
  type CheckpointItem,
} from "@/stores/context-engine-store";

export function VersionHistory() {
  const { token, orgId } = useAuthStore();
  const {
    activeRunId,
    checkpoints,
    isLoadingCheckpoints,
    isSavingCheckpoint,
    setCheckpoints,
    addCheckpoint,
    removeCheckpoint,
    setIsLoadingCheckpoints,
    setIsSavingCheckpoint,
    setTreeData,
    setIsLoadingTree,
  } = useContextEngineStore();

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [showLabelInput, setShowLabelInput] = useState(false);
  const [label, setLabel] = useState("");

  // Load checkpoints when active run changes
  useEffect(() => {
    if (!token || !activeRunId) {
      setCheckpoints([]);
      return;
    }
    const load = async () => {
      setIsLoadingCheckpoints(true);
      try {
        const data = await apiClient.get<{ checkpoints: CheckpointItem[] }>(
          `/api/context-engine/runs/${activeRunId}/checkpoints?org_id=${orgId}`,
          { token }
        );
        setCheckpoints(data.checkpoints);
      } catch {
        // ignore
      }
      setIsLoadingCheckpoints(false);
    };
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, activeRunId]);

  const handleSave = async () => {
    if (!token || !activeRunId) return;
    setIsSavingCheckpoint(true);
    try {
      const data = await apiClient.post<CheckpointItem>(
        `/api/context-engine/runs/${activeRunId}/checkpoint?org_id=${orgId}`,
        { label: label || "" },
        { token }
      );
      addCheckpoint(data);
      setLabel("");
      setShowLabelInput(false);
    } catch (e) {
      console.error("Failed to save checkpoint:", e);
    }
    setIsSavingCheckpoint(false);
  };

  const handleRestore = async (checkpointId: string) => {
    if (!token || !activeRunId) return;
    setRestoringId(checkpointId);
    try {
      const data = await apiClient.post<{
        tree_data: unknown;
        label: string;
      }>(
        `/api/context-engine/runs/${activeRunId}/checkpoint/${checkpointId}/restore?org_id=${orgId}`,
        {},
        { token }
      );
      if (data.tree_data) {
        setTreeData(data.tree_data as never);
      }
    } catch (e) {
      console.error("Failed to restore checkpoint:", e);
    }
    setRestoringId(null);
  };

  const handleDelete = async (checkpointId: string) => {
    if (!token || !activeRunId) return;
    if (!confirm("Delete this checkpoint? This cannot be undone.")) return;
    setDeletingId(checkpointId);
    try {
      await apiClient.delete(
        `/api/context-engine/runs/${activeRunId}/checkpoint/${checkpointId}?org_id=${orgId}`,
        { token }
      );
      removeCheckpoint(checkpointId);
    } catch (e) {
      console.error("Failed to delete checkpoint:", e);
    }
    setDeletingId(null);
  };

  if (!activeRunId) return null;

  return (
    <div className="border-b border-gray-200 p-4">
      {/* Header + Save button */}
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-semibold text-gray-600 uppercase tracking-wider flex items-center gap-1.5">
          <History className="h-3 w-3" />
          Versions
        </h3>
        <button
          onClick={() => {
            if (showLabelInput) {
              handleSave();
            } else {
              setShowLabelInput(true);
            }
          }}
          disabled={isSavingCheckpoint}
          className="flex items-center gap-1 rounded px-2 py-1 text-[11px] font-medium text-violet-600 hover:bg-violet-50 transition-colors disabled:opacity-50"
        >
          {isSavingCheckpoint ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <Save className="h-3 w-3" />
          )}
          Save
        </button>
      </div>

      {/* Label input (inline) */}
      {showLabelInput && (
        <div className="flex gap-1 mb-2">
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Checkpoint label (optional)"
            className="flex-1 rounded border border-gray-200 px-2 py-1 text-[11px] focus:border-violet-300 focus:ring-1 focus:ring-violet-200 outline-none"
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSave();
              if (e.key === "Escape") setShowLabelInput(false);
            }}
            autoFocus
          />
          <button
            onClick={() => setShowLabelInput(false)}
            className="text-[11px] text-gray-400 hover:text-gray-600 px-1"
          >
            Cancel
          </button>
        </div>
      )}

      {/* Checkpoint list */}
      {isLoadingCheckpoints ? (
        <div className="flex items-center justify-center py-3">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-gray-400" />
        </div>
      ) : checkpoints.length === 0 ? (
        <p className="text-[11px] text-gray-400">
          No saved versions yet. Click Save to create a checkpoint.
        </p>
      ) : (
        <div className="space-y-1 max-h-48 overflow-y-auto">
          {checkpoints.map((cp) => {
            const isExpanded = expandedId === cp.id;
            const isRestoring = restoringId === cp.id;
            const isDeleting = deletingId === cp.id;

            return (
              <div
                key={cp.id}
                className="rounded-lg border border-gray-100 bg-gray-50/50"
              >
                {/* Header row */}
                <div
                  className="flex items-center justify-between px-2.5 py-1.5 cursor-pointer hover:bg-gray-100/50 transition-colors"
                  onClick={() => setExpandedId(isExpanded ? null : cp.id)}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <Layers className="h-3 w-3 text-violet-400 shrink-0" />
                      <span className="text-[11px] font-medium text-gray-700 truncate">
                        {cp.label}
                      </span>
                    </div>
                    <p className="text-[10px] text-gray-400 ml-4.5">
                      {formatDate(cp.created_at)} &middot; {cp.leaf_count} leaves
                    </p>
                  </div>
                  <div className="flex items-center gap-0.5 shrink-0">
                    {isExpanded ? (
                      <ChevronUp className="h-3 w-3 text-gray-400" />
                    ) : (
                      <ChevronDown className="h-3 w-3 text-gray-400" />
                    )}
                  </div>
                </div>

                {/* Expanded details */}
                {isExpanded && (
                  <div className="px-2.5 pb-2 border-t border-gray-100">
                    <div className="flex items-center gap-3 mt-1.5 text-[10px] text-gray-500">
                      <span>Health: {cp.health_score}/100</span>
                      <span>Nodes: {cp.node_count}</span>
                    </div>
                    {cp.change_summary && (
                      <p className="text-[10px] text-gray-500 mt-1">
                        {cp.change_summary}
                      </p>
                    )}
                    <div className="flex gap-1 mt-2">
                      <button
                        onClick={() => handleRestore(cp.id)}
                        disabled={isRestoring || !!restoringId}
                        className={cn(
                          "flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium transition-colors",
                          "text-violet-600 hover:bg-violet-50 disabled:opacity-50"
                        )}
                      >
                        {isRestoring ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <RotateCcw className="h-3 w-3" />
                        )}
                        Restore
                      </button>
                      <button
                        onClick={() => handleDelete(cp.id)}
                        disabled={isDeleting || !!deletingId}
                        className="flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium text-red-500 hover:bg-red-50 transition-colors disabled:opacity-50"
                      >
                        {isDeleting ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <Trash2 className="h-3 w-3" />
                        )}
                        Delete
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
