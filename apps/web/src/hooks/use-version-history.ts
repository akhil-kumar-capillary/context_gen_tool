"use client";

import { useState, useCallback, useRef } from "react";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import type { VersionSummary, VersionDetail } from "@/types";

interface UseVersionHistoryReturn {
  versions: VersionSummary[];
  total: number;
  hasMore: boolean;
  isLoading: boolean;
  error: string | null;
  isRestoring: boolean;
  fetchHistory: (reset?: boolean) => Promise<void>;
  fetchVersionDetail: (versionNumber: number) => Promise<VersionDetail | null>;
  restoreVersion: (versionNumber: number, currentVersion?: number) => Promise<boolean>;
}

const PAGE_SIZE = 50;

export function useVersionHistory(
  entityType: string,
  entityId: string | null,
): UseVersionHistoryReturn {
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isRestoring, setIsRestoring] = useState(false);

  // Use ref for offset to avoid stale closures in fetchHistory
  const versionsRef = useRef(versions);
  versionsRef.current = versions;

  const fetchHistory = useCallback(
    async (reset = true) => {
      const { token, orgId } = useAuthStore.getState();
      if (!token || !orgId || !entityId) return;

      setIsLoading(true);
      setError(null);
      try {
        const offset = reset ? 0 : versionsRef.current.length;
        const data = await apiClient.get<{
          versions: VersionSummary[];
          total: number;
          has_more: boolean;
        }>(
          `/api/versions/${entityType}/${entityId}/history?org_id=${orgId}&limit=${PAGE_SIZE}&offset=${offset}`,
          { token },
        );
        if (reset) {
          setVersions(data.versions);
        } else {
          setVersions((prev) => [...prev, ...data.versions]);
        }
        setTotal(data.total);
        setHasMore(data.has_more);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load version history");
      }
      setIsLoading(false);
    },
    [entityType, entityId],
  );

  const fetchVersionDetail = useCallback(
    async (versionNumber: number): Promise<VersionDetail | null> => {
      const { token, orgId } = useAuthStore.getState();
      if (!token || !orgId || !entityId) return null;

      try {
        return await apiClient.get<VersionDetail>(
          `/api/versions/${entityType}/${entityId}/${versionNumber}?org_id=${orgId}`,
          { token },
        );
      } catch {
        return null;
      }
    },
    [entityType, entityId],
  );

  const restoreVersion = useCallback(
    async (versionNumber: number, currentVersion?: number): Promise<boolean> => {
      const { token, orgId } = useAuthStore.getState();
      if (!token || !orgId || !entityId) return false;

      setIsRestoring(true);
      try {
        await apiClient.post(
          `/api/versions/${entityType}/${entityId}/restore/${versionNumber}?org_id=${orgId}`,
          entityType === "context_tree" ? { version: currentVersion } : {},
          { token },
        );
        setIsRestoring(false);
        return true;
      } catch {
        setIsRestoring(false);
        return false;
      }
    },
    [entityType, entityId],
  );

  return {
    versions,
    total,
    hasMore,
    isLoading,
    error,
    isRestoring,
    fetchHistory,
    fetchVersionDetail,
    restoreVersion,
  };
}
