"use client";

import { memo } from "react";
import { Pencil, Archive, ArchiveRestore, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useContextStore } from "@/stores/context-store";
import { ScopeBadge } from "./scope-badge";
import type { Context } from "@/types";

function stripHtml(text: string): string {
  return text.replace(/<[^>]+>/g, "");
}

function truncate(text: string, maxLen: number): string {
  const clean = stripHtml(text);
  if (clean.length <= maxLen) return clean;
  return clean.slice(0, maxLen) + "...";
}

interface ContextRowProps {
  ctx: Context;
}

export const ContextRow = memo(function ContextRow({ ctx }: ContextRowProps) {
  const {
    confirmArchiveId,
    actionLoadingId,
    setEditingContextId,
    setConfirmArchiveId,
    archiveContext,
    restoreContext,
  } = useContextStore();

  const isConfirmingArchive = confirmArchiveId === ctx.id;
  const isActionLoading = actionLoadingId === ctx.id;
  const canEdit = ctx.can_edit !== false;
  const isArchived = ctx.is_active === false;

  return (
    <div className="border-b border-gray-100 last:border-0">
      <div className="grid grid-cols-[1fr_70px_1.2fr_120px] items-center gap-3 px-4 py-3">
        {/* Name + preview */}
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className={cn("truncate text-sm font-medium", isArchived ? "text-gray-400" : "text-gray-900")}>
              {ctx.name}
            </p>
            {isArchived && (
              <span className="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-400">
                Archived
              </span>
            )}
          </div>
          <p className="mt-0.5 truncate text-xs text-gray-400">
            {truncate(ctx.context || "", 80)}
          </p>
        </div>

        {/* Scope */}
        <ScopeBadge scope={ctx.scope} />

        {/* Updated by */}
        <p className="truncate text-xs text-gray-500">{ctx.updated_by || "—"}</p>

        {/* Actions */}
        <div className="flex items-center justify-end gap-1">
          {canEdit && !isArchived && (
            <>
              <button
                onClick={() => setEditingContextId(ctx.id)}
                className="rounded-md p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                title="Edit"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => setConfirmArchiveId(ctx.id)}
                className="rounded-md p-1.5 text-gray-400 transition-colors hover:bg-amber-50 hover:text-amber-600"
                title="Archive"
              >
                <Archive className="h-3.5 w-3.5" />
              </button>
            </>
          )}
          {canEdit && isArchived && (
            <button
              onClick={() => restoreContext(ctx.id)}
              disabled={!!actionLoadingId}
              className="rounded-md p-1.5 text-gray-400 transition-colors hover:bg-green-50 hover:text-green-600 disabled:pointer-events-none"
              title="Restore"
            >
              {isActionLoading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-green-500" />
              ) : (
                <ArchiveRestore className="h-3.5 w-3.5" />
              )}
            </button>
          )}
        </div>
      </div>

      {/* Archive confirmation */}
      {isConfirmingArchive && (
        <div className="mx-4 mb-3 flex items-center justify-between rounded-lg bg-amber-50 px-4 py-2.5 border border-amber-200">
          <p className="text-sm text-amber-800">
            Archive <strong>{ctx.name}</strong>? It can be restored later.
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setConfirmArchiveId(null)}
              disabled={isActionLoading}
              className="rounded-md px-3 py-1 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-100 disabled:pointer-events-none"
            >
              Cancel
            </button>
            <button
              onClick={() => archiveContext(ctx.id)}
              disabled={isActionLoading}
              className="rounded-md bg-amber-600 px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-amber-700 disabled:opacity-70 disabled:pointer-events-none"
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
