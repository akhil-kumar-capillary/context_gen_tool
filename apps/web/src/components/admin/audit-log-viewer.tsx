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
    return "bg-gray-100 text-gray-600";
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">
          Recent administrative actions and system events.
        </p>
        <button
          onClick={() => fetchAuditLogs(pageSize, page * pageSize)}
          disabled={auditLoading}
          className="rounded-lg border border-gray-200 p-2 text-gray-500 hover:bg-gray-50"
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
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
        </div>
      )}

      {!auditLoading && auditLogs.length === 0 && (
        <div className="rounded-xl border border-gray-200 bg-white px-5 py-12 text-center">
          <ScrollText className="mx-auto h-8 w-8 text-gray-300" />
          <p className="mt-2 text-sm text-gray-400">
            No audit logs recorded yet.
          </p>
        </div>
      )}

      {!auditLoading && auditLogs.length > 0 && (
        <>
          <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
            <div className="grid grid-cols-12 gap-3 bg-gray-50 px-5 py-2.5 text-xs font-medium uppercase tracking-wide text-gray-500">
              <div className="col-span-3">User</div>
              <div className="col-span-2">Action</div>
              <div className="col-span-2">Module</div>
              <div className="col-span-2">Resource</div>
              <div className="col-span-2">Date</div>
              <div className="col-span-1"></div>
            </div>

            {auditLogs.map((log) => (
              <div key={log.id} className="border-b border-gray-100 last:border-0">
                <div className="grid grid-cols-12 gap-3 px-5 py-2.5 items-center hover:bg-gray-50 transition-colors">
                  <div className="col-span-3 truncate text-sm text-gray-900">
                    {log.user_email || "System"}
                  </div>
                  <div className="col-span-2">
                    <span
                      className={cn(
                        "inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium",
                        actionColor(log.action)
                      )}
                    >
                      {log.action}
                    </span>
                  </div>
                  <div className="col-span-2 text-xs text-gray-500">
                    {log.module || "—"}
                  </div>
                  <div className="col-span-2 text-xs text-gray-500 truncate">
                    {log.resource_type
                      ? `${log.resource_type}:${log.resource_id}`
                      : "—"}
                  </div>
                  <div className="col-span-2 text-xs text-gray-400">
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
                        className="rounded-md p-1 text-gray-400 hover:bg-gray-100"
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
                  <div className="border-t border-gray-100 bg-gray-50/50 px-5 py-3">
                    <pre className="whitespace-pre-wrap text-xs text-gray-600 font-mono">
                      {JSON.stringify(log.details, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between">
            <p className="text-xs text-gray-400">
              Showing {page * pageSize + 1} -{" "}
              {page * pageSize + auditLogs.length} entries
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(Math.max(0, page - 1))}
                disabled={page === 0}
                className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50"
              >
                Previous
              </button>
              <button
                onClick={() => setPage(page + 1)}
                disabled={auditLogs.length < pageSize}
                className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50"
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
