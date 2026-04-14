"use client";

import { useEffect } from "react";
import { Plus, Loader2, RefreshCw, Download, FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import { useContextStore, type ContextStatusFilter } from "@/stores/context-store";
import { useAuthStore } from "@/stores/auth-store";
import { downloadAllContexts } from "@/lib/utils";
import { ContextRow } from "./context-row";
import { NewContextDialog } from "./new-context-dialog";
import { TableSkeleton } from "@/components/ui/skeleton";
import { EditContextDialog } from "./edit-context-dialog";
import { ContextVersionDialog } from "./context-version-dialog";

const STATUS_OPTIONS: { value: ContextStatusFilter; label: string }[] = [
  { value: "active", label: "Active" },
  { value: "archived", label: "Archived" },
  { value: "all", label: "All" },
];

export function ContextTable() {
  const { orgName } = useAuthStore();
  const {
    contexts,
    isLoading,
    error,
    editingContextId,
    isCreating,
    statusFilter,
    fetchContexts,
    setIsCreating,
    setStatusFilter,
  } = useContextStore();

  useEffect(() => {
    fetchContexts();
  }, [fetchContexts, statusFilter]);

  const editingCtx = editingContextId
    ? contexts.find((c) => c.id === editingContextId)
    : null;

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="mb-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          {/* Segmented control filter */}
          <div className="flex items-center rounded-lg border border-border bg-muted/50 p-0.5">
            {STATUS_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setStatusFilter(opt.value)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-xs font-medium transition-all",
                  statusFilter === opt.value
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <span className="text-xs text-muted-foreground">
            {contexts.length} context{contexts.length !== 1 ? "s" : ""}
          </span>

          <button
            onClick={() => fetchContexts()}
            disabled={isLoading}
            className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
            aria-label="Refresh context list"
          >
            <RefreshCw className={cn("h-4 w-4", isLoading && "animate-spin")} />
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsCreating(true)}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
          >
            <Plus className="h-3.5 w-3.5" />
            New Context
          </button>
          <button
            onClick={() => downloadAllContexts(contexts, orgName)}
            disabled={contexts.length === 0 || isLoading}
            className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
          >
            <Download className="h-3.5 w-3.5" />
            Download All
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 rounded-lg border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Table — scrolls internally */}
      <div className="flex-1 min-h-0 rounded-lg border border-border bg-background overflow-hidden flex flex-col">
        {/* Column headers — sticky */}
        <div className="grid grid-cols-[1fr_70px_1fr_140px] gap-3 border-b border-border bg-muted/50 px-4 py-2.5 shrink-0">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Name
          </span>
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Scope
          </span>
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider hidden sm:block">
            Updated By
          </span>
          <span className="text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Actions
          </span>
        </div>

        {/* Scrollable rows area */}
        <div className="flex-1 overflow-y-auto">
        {/* Loading skeleton */}
        {isLoading && contexts.length === 0 && (
          <div className="p-4">
            <TableSkeleton rows={4} />
          </div>
        )}

        {/* Empty state */}
        {!isLoading && contexts.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted mb-3">
              <FileText className="h-6 w-6 text-muted-foreground" />
            </div>
            <p className="text-sm font-medium text-foreground">
              {statusFilter === "archived" ? "No archived contexts" : "No contexts found"}
            </p>
            {statusFilter === "active" && (
              <>
                <p className="mt-1 text-xs text-muted-foreground">
                  Create your first context or use the chat to manage them.
                </p>
                <button
                  onClick={() => setIsCreating(true)}
                  className="mt-4 flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
                >
                  <Plus className="h-3.5 w-3.5" />
                  New Context
                </button>
              </>
            )}
          </div>
        )}

        {/* Rows */}
        {contexts.map((ctx) => (
          <ContextRow key={ctx.id} ctx={ctx} />
        ))}
        </div>
      </div>

      {/* Modals */}
      {isCreating && <NewContextDialog />}
      {editingCtx && <EditContextDialog ctx={editingCtx} />}
      <ContextVersionDialog />
    </div>
  );
}
