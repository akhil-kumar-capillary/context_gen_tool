"use client";

import { useEffect } from "react";
import { Plus, Loader2, RefreshCw } from "lucide-react";
import { useContextStore } from "@/stores/context-store";
import { ContextRow } from "./context-row";
import { NewContextDialog } from "./new-context-dialog";
import { EditContextDialog } from "./edit-context-dialog";

export function ContextTable() {
  const {
    contexts,
    isLoading,
    error,
    editingContextId,
    isCreating,
    fetchContexts,
    setIsCreating,
  } = useContextStore();

  useEffect(() => {
    fetchContexts();
  }, [fetchContexts]);

  const editingCtx = editingContextId
    ? contexts.find((c) => c.id === editingContextId)
    : null;

  return (
    <div>
      {/* Header row */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wider text-gray-400">
            {contexts.length} context{contexts.length !== 1 ? "s" : ""}
          </span>
          <button
            onClick={() => fetchContexts()}
            disabled={isLoading}
            className="rounded-md p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? "animate-spin" : ""}`} />
          </button>
        </div>
        <button
          onClick={() => setIsCreating(true)}
          className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-violet-700"
        >
          <Plus className="h-3.5 w-3.5" />
          New Context
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-3 rounded-lg bg-red-50 px-4 py-2.5 text-sm text-red-600">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="rounded-lg border border-gray-200 bg-white">
        {/* Column headers */}
        <div className="grid grid-cols-[1fr_70px_1.2fr_120px] gap-3 border-b border-gray-200 bg-gray-50 px-4 py-2">
          <span className="text-xs font-medium uppercase tracking-wider text-gray-500">
            Name
          </span>
          <span className="text-xs font-medium uppercase tracking-wider text-gray-500">
            Scope
          </span>
          <span className="text-xs font-medium uppercase tracking-wider text-gray-500">
            Updated By
          </span>
          <span className="text-right text-xs font-medium uppercase tracking-wider text-gray-500">
            Actions
          </span>
        </div>

        {/* Loading */}
        {isLoading && contexts.length === 0 && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
            <span className="ml-2 text-sm text-gray-400">Loading contexts...</span>
          </div>
        )}

        {/* Empty state */}
        {!isLoading && contexts.length === 0 && (
          <div className="py-12 text-center">
            <p className="text-sm text-gray-400">No contexts found</p>
            <p className="mt-1 text-xs text-gray-400">
              Create your first context or use the chat to manage them.
            </p>
          </div>
        )}

        {/* Rows */}
        {contexts.map((ctx) => (
          <ContextRow key={ctx.id} ctx={ctx} />
        ))}
      </div>

      {/* Modals */}
      {isCreating && <NewContextDialog />}
      {editingCtx && <EditContextDialog ctx={editingCtx} />}
    </div>
  );
}
