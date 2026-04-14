"use client";

import { useEffect, useState } from "react";
import { useAdminStore } from "@/stores/admin-store";
import { Loader2, RefreshCw, ScrollText, ChevronDown, ChevronUp } from "lucide-react";
import { cn, formatDate } from "@/lib/utils";

export function AuditLogViewer() {
  const { auditLogs, auditLoading, auditError, fetchAuditLogs } =
    useAdminStore();
  const [expandedLog, setExpandedLog] = useState<number | null>(null);
  const [page, setPage] = useState(0);
  const pageSize = 50;

  useEffect(() => {
    fetchAuditLogs(pageSize, page * pageSize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  const actionColor = (action: string) => {
    if (action.includes("delete") || action.includes("revoke"))
      return "bg-red-100 text-red-700";
    if (action.includes("create") || action.includes("grant"))
      return "bg-green-100 text-green-700";
    if (action.includes("update") || action.includes("edit"))
      return "bg-blue-100 text-blue-700";
    return "bg-muted text-muted-foreground";
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Recent administrative actions and system events.
        </p>
        <button
          onClick={() => fetchAuditLogs(pageSize, page * pageSize)}
          disabled={auditLoading}
          className="rounded-lg border border-border p-2 text-muted-foreground hover:bg-muted/50"
        >
          <RefreshCw
            className={cn("h-4 w-4", auditLoading && "animate-spin")}
          />
        </button>
      </div>

      {auditError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {auditError}
        </div>
      )}

      {auditLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}

      {!auditLoading && auditLogs.length === 0 && (
        <div className="rounded-xl border border-border bg-background px-5 py-12 text-center">
          <ScrollText className="mx-auto h-8 w-8 text-muted-foreground/50" />
          <p className="mt-2 text-sm text-muted-foreground">
            No audit logs recorded yet.
          </p>
        </div>
      )}

      {!auditLoading && auditLogs.length > 0 && (
        <>
          <div className="rounded-xl border border-border bg-background overflow-hidden">
            <div className="grid grid-cols-12 gap-3 bg-muted/50 px-5 py-2.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              <div className="col-span-3">User</div>
              <div className="col-span-2">Action</div>
              <div className="col-span-2">Module</div>
              <div className="col-span-2">Resource</div>
              <div className="col-span-2">Date</div>
              <div className="col-span-1"></div>
            </div>

            {auditLogs.map((log) => (
              <div key={log.id} className="border-b border-border last:border-0">
                <div className="grid grid-cols-12 gap-3 px-5 py-2.5 items-center hover:bg-muted/50 transition-colors">
                  <div className="col-span-3 truncate text-sm text-foreground">
                    {log.user_email || "System"}
                  </div>
                  <div className="col-span-2">
                    <span
                      className={cn(
                        "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
                        actionColor(log.action)
                      )}
                    >
                      {log.action}
                    </span>
                  </div>
                  <div className="col-span-2 text-xs text-muted-foreground">
                    {log.module || "—"}
                  </div>
                  <div className="col-span-2 text-xs text-muted-foreground truncate">
                    {log.resource_type
                      ? `${log.resource_type}:${log.resource_id}`
                      : "—"}
                  </div>
                  <div className="col-span-2 text-xs text-muted-foreground">
                    {formatDate(log.created_at)}
                  </div>
                  <div className="col-span-1 text-right">
                    {log.details && (
                      <button
                        onClick={() =>
                          setExpandedLog(
                            expandedLog === log.id ? null : log.id
                          )
                        }
                        className="rounded-md p-1 text-muted-foreground hover:bg-muted"
                      >
                        {expandedLog === log.id ? (
                          <ChevronUp className="h-3.5 w-3.5" />
                        ) : (
                          <ChevronDown className="h-3.5 w-3.5" />
                        )}
                      </button>
                    )}
                  </div>
                </div>

                {expandedLog === log.id && log.details && (
                  <div className="border-t border-border bg-muted/50 px-5 py-3">
                    <pre className="whitespace-pre-wrap text-xs text-muted-foreground font-mono">
                      {JSON.stringify(log.details, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground">
              Showing {page * pageSize + 1} -{" "}
              {page * pageSize + auditLogs.length} entries
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(Math.max(0, page - 1))}
                disabled={page === 0}
                className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted/50 disabled:opacity-50"
              >
                Previous
              </button>
              <button
                onClick={() => setPage(page + 1)}
                disabled={auditLogs.length < pageSize}
                className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted/50 disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
