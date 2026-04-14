"use client";

import {
  useContextEngineStore,
  type ContextTreeNode,
} from "@/stores/context-engine-store";
import { VersionHistoryPanel } from "@/components/shared/version-history-panel";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";

export function VersionHistory() {
  const { activeRunId, treeRuns, setTreeData } = useContextEngineStore();
  const { token, orgId } = useAuthStore();

  if (!activeRunId) return null;

  const activeRun = treeRuns.find((r) => r.id === activeRunId);

  const handleRestore = async () => {
    if (!token || !activeRunId) return;
    try {
      const data = await apiClient.get<{ tree_data: ContextTreeNode; version: number }>(
        `/api/context-engine/runs/${activeRunId}?org_id=${orgId}`,
        { token },
      );
      if (data.tree_data) {
        setTreeData(data.tree_data);
      }
    } catch {
      // Handled by the panel's toast
    }
  };

  return (
    <VersionHistoryPanel
      entityType="context_tree"
      entityId={activeRunId}
      currentVersion={activeRun?.version}
      onRestore={handleRestore}
    />
  );
}
