"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Loader2,
  History,
  RotateCcw,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import { useVersionHistory } from "@/hooks/use-version-history";
import type { VersionSummary } from "@/types";

interface VersionHistoryPanelProps {
  entityType: string;
  entityId: string | null;
  currentVersion?: number;
  onRestore?: () => void;
}

const CHANGE_BADGES: Record<string, { bg: string; text: string; label: string }> = {
  create: { bg: "bg-green-100", text: "text-green-700", label: "Created" },
  update: { bg: "bg-blue-100", text: "text-blue-700", label: "Updated" },
  add_node: { bg: "bg-green-100", text: "text-green-700", label: "Node Added" },
  update_node: { bg: "bg-blue-100", text: "text-blue-700", label: "Node Updated" },
  delete_node: { bg: "bg-red-100", text: "text-red-700", label: "Node Deleted" },
  restructure: { bg: "bg-purple-100", text: "text-purple-700", label: "Restructured" },
  archive: { bg: "bg-amber-100", text: "text-amber-700", label: "Archived" },
  restore: { bg: "bg-primary/10", text: "text-primary", label: "Restored" },
  version_restore: { bg: "bg-primary/10", text: "text-primary", label: "Version Restored" },
  checkpoint_restore: { bg: "bg-primary/10", text: "text-primary", label: "Checkpoint Restored" },
};

function ChangeBadge({ changeType }: { changeType: string }) {
  const badge = CHANGE_BADGES[changeType] || { bg: "bg-muted", text: "text-muted-foreground", label: changeType };
  return (
    <span className={cn("rounded px-1.5 py-0.5 text-xs font-medium", badge.bg, badge.text)}>
      {badge.label}
    </span>
  );
}

export function VersionHistoryPanel({
  entityType,
  entityId,
  currentVersion,
  onRestore,
}: VersionHistoryPanelProps) {
  const {
    versions,
    hasMore,
    isLoading,
    isRestoring,
    fetchHistory,
    restoreVersion,
  } = useVersionHistory(entityType, entityId);

  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    if (entityId) fetchHistory(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entityId]);

  const handleRestore = async (v: VersionSummary) => {
    const ok = await restoreVersion(v.version_number, currentVersion);
    if (ok) {
      toast.success(`Restored to version ${v.version_number}`);
      onRestore?.();
      fetchHistory(true);
    } else {
      toast.error("Failed to restore version");
    }
  };

  if (!entityId) return null;

  return (
    <div className="border-b border-border p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
          <History className="h-3 w-3" />
          Version History
        </h3>
      </div>

      {isLoading && versions.length === 0 ? (
        <div className="flex items-center justify-center py-3">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
        </div>
      ) : versions.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No version history yet. Changes will be tracked automatically.
        </p>
      ) : (
        <div className="space-y-1 max-h-64 overflow-y-auto">
          {versions.map((v) => {
            const isExpanded = expandedId === v.id;
            return (
              <div key={v.id} className="rounded-lg border border-border bg-muted/50">
                <div
                  className="flex items-center justify-between px-2.5 py-1.5 cursor-pointer hover:bg-muted/50 transition-colors"
                  onClick={() => setExpandedId(isExpanded ? null : v.id)}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-mono text-muted-foreground shrink-0">v{v.version_number}</span>
                      <ChangeBadge changeType={v.change_type} />
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5 truncate">{v.change_summary || v.change_type}</p>
                    <p className="text-xs text-muted-foreground">{formatDate(v.created_at)}</p>
                  </div>
                  <div className="shrink-0">
                    {isExpanded ? <ChevronUp className="h-3 w-3 text-muted-foreground" /> : <ChevronDown className="h-3 w-3 text-muted-foreground" />}
                  </div>
                </div>
                {isExpanded && (
                  <div className="px-2.5 pb-2 border-t border-border">
                    {v.changed_fields && v.changed_fields.length > 0 && (
                      <p className="text-xs text-muted-foreground mt-1.5">Fields: {v.changed_fields.join(", ")}</p>
                    )}
                    <div className="flex gap-1 mt-2">
                      <button
                        onClick={() => handleRestore(v)}
                        disabled={isRestoring}
                        className="flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-primary hover:bg-primary/5 transition-colors disabled:opacity-50"
                      >
                        {isRestoring ? <Loader2 className="h-3 w-3 animate-spin" /> : <RotateCcw className="h-3 w-3" />}
                        Restore
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
          {hasMore && (
            <button
              onClick={() => fetchHistory(false)}
              disabled={isLoading}
              className="w-full rounded-lg border border-border py-1.5 text-xs text-muted-foreground hover:bg-muted/50 transition-colors disabled:opacity-50"
            >
              {isLoading ? <Loader2 className="h-3 w-3 animate-spin inline mr-1" /> : null}
              Load more
            </button>
          )}
        </div>
      )}
    </div>
  );
}
