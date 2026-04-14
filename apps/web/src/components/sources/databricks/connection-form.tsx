"use client";

import { useState, useEffect } from "react";
import {
  Loader2,
  CheckCircle,
  XCircle,
  Link,
  Server,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import { useDatabricksStore } from "@/stores/databricks-store";

export function ConnectionForm() {
  const { token, cluster: authCluster } = useAuthStore();
  const {
    connection,
    connectionStatus,
    connectionError,
    setConnection,
    setConnectionStatus,
    setActiveStep,
  } = useDatabricksStore();

  const [isTesting, setIsTesting] = useState(false);

  // Fetch the user's auto-resolved cluster info on mount
  useEffect(() => {
    if (!token || !authCluster) return;
    if (connection.cluster && connection.instance) return; // already resolved
    let cancelled = false;

    const fetchMyCluster = async () => {
      try {
        const data = await apiClient.get<{
          cluster_key: string;
          instance: string | null;
          configured: boolean;
          message?: string;
        }>("/api/sources/databricks/my-cluster", { token });
        if (!cancelled && data.configured && data.instance) {
          setConnection({
            cluster: data.cluster_key,
            instance: data.instance,
          });
        } else if (!cancelled && !data.configured) {
          setConnectionStatus("failed", data.message || "Cluster not configured");
        }
      } catch (err) {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : "Failed to resolve cluster";
          setConnectionStatus("failed", msg);
        }
      }
    };

    fetchMyCluster();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, authCluster]);

  // Auto-test connection once cluster is resolved
  useEffect(() => {
    if (
      connection.cluster &&
      connection.instance &&
      connectionStatus === "idle" &&
      !isTesting
    ) {
      handleTest();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connection.cluster, connection.instance]);

  const handleTest = async () => {
    if (!connection.cluster) return;

    setIsTesting(true);
    setConnectionStatus("testing");

    try {
      const result = await apiClient.post<{ success: boolean; message: string }>(
        "/api/sources/databricks/test-connection",
        {},
        { token: token || undefined }
      );
      if (result.success) {
        setConnectionStatus("connected");
      } else {
        setConnectionStatus("failed", result.message || "Connection failed");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Connection failed";
      setConnectionStatus("failed", msg);
    } finally {
      setIsTesting(false);
    }
  };

  const canProceed = connectionStatus === "connected";

  return (
    <div className="rounded-xl border border-border bg-background p-6">
      <div className="mb-4 flex items-center gap-2">
        <Link className="h-5 w-5 text-primary" />
        <h2 className="text-lg font-semibold text-foreground">Databricks Connection</h2>
      </div>

      <div className="space-y-4">
        {/* Cluster info (read-only, auto-resolved from login) */}
        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">
            Cluster
          </label>
          <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
            <span className="font-medium text-foreground">
              {connection.cluster || authCluster?.toUpperCase() || "—"}
            </span>
            <span className="text-muted-foreground">·</span>
            <span className="text-xs text-muted-foreground">auto-resolved from login</span>
          </div>
        </div>

        {/* Instance URL display (read-only) */}
        {connection.instance && (
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">
              Workspace URL
            </label>
            <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
              <Server className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="truncate">{connection.instance}</span>
            </div>
          </div>
        )}

        {/* Connection status + retry */}
        <div className="flex items-center gap-3">
          {connectionStatus === "testing" && (
            <span className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Testing connection...
            </span>
          )}

          {connectionStatus === "connected" && (
            <span className="flex items-center gap-1.5 text-sm text-green-600">
              <CheckCircle className="h-4 w-4" />
              Connected
            </span>
          )}

          {connectionStatus === "failed" && (
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-1.5 text-sm text-red-500">
                <XCircle className="h-4 w-4" />
                {connectionError || "Failed"}
              </span>
              <button
                onClick={handleTest}
                disabled={isTesting || !connection.cluster}
                className={cn(
                  "rounded-lg px-3 py-1.5 text-xs font-medium transition-all",
                  isTesting || !connection.cluster
                    ? "bg-muted text-muted-foreground"
                    : "bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm"
                )}
              >
                Retry
              </button>
            </div>
          )}
        </div>

        {canProceed && (
          <button
            onClick={() => setActiveStep("extract")}
            className="mt-2 w-full rounded-lg bg-primary py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:bg-primary/90"
          >
            Continue to Extraction
          </button>
        )}
      </div>
    </div>
  );
}
