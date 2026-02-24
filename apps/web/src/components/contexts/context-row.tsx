"use client";

import { memo } from "react";
import { Pencil, Trash2 } from "lucide-react";
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
  const { confirmDeleteId, setEditingContextId, setConfirmDeleteId, deleteContext } =
    useContextStore();

  const isConfirmingDelete = confirmDeleteId === ctx.id;
  const canEdit = ctx.can_edit !== false;

  return (
    <div className="border-b border-gray-100 last:border-0">
      <div className="grid grid-cols-[1fr_70px_1.2fr_120px] items-center gap-3 px-4 py-3">
        {/* Name + preview */}
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-gray-900">{ctx.name}</p>
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
          {canEdit && (
            <>
              <button
                onClick={() => setEditingContextId(ctx.id)}
                className="rounded-md p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                title="Edit"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => setConfirmDeleteId(ctx.id)}
                className="rounded-md p-1.5 text-gray-400 transition-colors hover:bg-red-50 hover:text-red-500"
                title="Delete"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Delete confirmation */}
      {isConfirmingDelete && (
        <div className="mx-4 mb-3 flex items-center justify-between rounded-lg bg-amber-50 px-4 py-2.5 border border-amber-200">
          <p className="text-sm text-amber-800">
            Delete <strong>{ctx.name}</strong>? This cannot be undone.
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setConfirmDeleteId(null)}
              className="rounded-md px-3 py-1 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-100"
            >
              Cancel
            </button>
            <button
              onClick={() => deleteContext(ctx.id)}
              className="rounded-md bg-red-600 px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-red-700"
            >
              Delete
            </button>
          </div>
        </div>
      )}
    </div>
  );
});
