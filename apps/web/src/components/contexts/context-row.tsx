"use client";

import { memo } from "react";
import { Pencil, Archive, ArchiveRestore, Loader2, History } from "lucide-react";
import { cn } from "@/lib/utils";
import { truncateHtml } from "@/lib/text-utils";
import { useContextStore } from "@/stores/context-store";
import { ScopeBadge } from "./scope-badge";
import type { Context } from "@/types";

interface ContextRowProps {
  ctx: Context;
}

export const ContextRow = memo(function ContextRow({ ctx }: ContextRowProps) {
  const {
    confirmArchiveId,
    actionLoadingId,
    setEditingContextId,
    setConfirmArchiveId,
    setVersionHistoryContextId,
    archiveContext,
    restoreContext,
  } = useContextStore();

  const isConfirmingArchive = confirmArchiveId === ctx.id;
  const isActionLoading = actionLoadingId === ctx.id;
  const canEdit = ctx.can_edit !== false;
  const isArchived = ctx.is_active === false;

  return (
    <div className="border-b border-border last:border-0 transition-colors hover:bg-muted/30">
      <div className="grid grid-cols-[1fr_70px_1fr_140px] items-center gap-3 px-4 py-3">
        {/* Name + preview */}
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className={cn("truncate text-sm font-medium", isArchived ? "text-muted-foreground" : "text-foreground")}>
              {ctx.name}
            </p>
            {isArchived && (
              <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-xs font-medium text-muted-foreground">
                Archived
              </span>
            )}
          </div>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">
            {truncateHtml(ctx.context || "", 80)}
          </p>
        </div>

        {/* Scope */}
        <ScopeBadge scope={ctx.scope} />

        {/* Updated by */}
        <p className="truncate text-xs text-muted-foreground hidden sm:block">{ctx.updated_by || "\u2014"}</p>

        {/* Actions */}
        <div className="flex items-center justify-end gap-0.5">
          {canEdit && !isArchived && (
            <>
              <button
                onClick={() => setEditingContextId(ctx.id)}
                className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                aria-label={`Edit ${ctx.name}`}
              >
                <Pencil className="h-4 w-4" />
              </button>
              <button
                onClick={() => setVersionHistoryContextId(ctx.id)}
                className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-primary/5 hover:text-primary"
                aria-label={`Version history for ${ctx.name}`}
              >
                <History className="h-4 w-4" />
              </button>
              <button
                onClick={() => setConfirmArchiveId(ctx.id)}
                className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-destructive/5 hover:text-destructive"
                aria-label={`Archive ${ctx.name}`}
              >
                <Archive className="h-4 w-4" />
              </button>
            </>
          )}
          {canEdit && isArchived && (
            <button
              onClick={() => restoreContext(ctx.id)}
              disabled={!!actionLoadingId}
              className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-green-50 hover:text-green-600 disabled:pointer-events-none"
              aria-label={`Restore ${ctx.name}`}
            >
              {isActionLoading ? (
                <Loader2 className="h-4 w-4 animate-spin text-green-500" />
              ) : (
                <ArchiveRestore className="h-4 w-4" />
              )}
            </button>
          )}
        </div>
      </div>

      {/* Archive confirmation */}
      {isConfirmingArchive && (
        <div className="mx-4 mb-3 flex items-center justify-between rounded-lg border border-destructive/20 bg-destructive/5 px-4 py-2.5">
          <p className="text-sm text-destructive">
            Archive <strong>{ctx.name}</strong>? It can be restored later.
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setConfirmArchiveId(null)}
              disabled={isActionLoading}
              className="rounded-md px-3 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted disabled:pointer-events-none"
            >
              Cancel
            </button>
            <button
              onClick={() => archiveContext(ctx.id)}
              disabled={isActionLoading}
              className="rounded-md bg-destructive px-3 py-1 text-xs font-medium text-destructive-foreground transition-colors hover:bg-destructive/90 disabled:opacity-70 disabled:pointer-events-none"
            >
              {isActionLoading ? (
                <span className="flex items-center gap-1.5">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Archiving...
                </span>
              ) : (
                "Archive"
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
});
