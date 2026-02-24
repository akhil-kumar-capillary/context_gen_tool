"use client";

import { useState, useCallback } from "react";
import { Sparkles, Upload, X, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useContextStore } from "@/stores/context-store";
import { useChatStore } from "@/stores/chat-store";
import { ContextTable } from "./context-table";
import { AiContextRow } from "./ai-context-row";
import { EditAiContextDialog } from "./edit-ai-context-dialog";

type ViewMode = "contexts" | "ai-generated";

interface ContextPanelProps {
  onSendChatMessage?: (content: string) => void;
}

export function ContextPanel({ onSendChatMessage }: ContextPanelProps) {
  const [viewMode, setViewMode] = useState<ViewMode>("contexts");

  const {
    aiContexts,
    sanitizeUsage,
    editingContextId,
    bulkUpload,
    dismissAiContexts,
  } = useContextStore();

  const { isStreaming } = useChatStore();

  const editingAiCtx = editingContextId
    ? aiContexts?.find((c) => c.id === editingContextId)
    : null;

  const allUploaded = aiContexts?.every((c) => c.uploadStatus === "success") ?? false;
  const someUploading = aiContexts?.some((c) => c.uploadStatus === "uploading") ?? false;
  const pendingCount =
    aiContexts?.filter((c) => c.uploadStatus !== "success" && c.uploadStatus !== "uploading")
      .length ?? 0;

  const handleSanitize = useCallback(() => {
    if (onSendChatMessage) {
      setViewMode("ai-generated");
      onSendChatMessage(
        "Please refactor and sanitize all my contexts using the blueprint. Restructure them into well-organized documents following best practices."
      );
    }
  }, [onSendChatMessage]);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Context Management</h1>
        <p className="text-sm text-gray-500">
          Manage, create, and refactor context documents for your organization.
        </p>
      </div>

      {/* Tab toggle */}
      <div className="flex items-center gap-1 rounded-lg bg-gray-100 p-1 w-fit">
        <button
          onClick={() => setViewMode("contexts")}
          className={cn(
            "rounded-md px-4 py-1.5 text-sm font-medium transition-colors",
            viewMode === "contexts"
              ? "bg-white text-gray-900 shadow-sm"
              : "text-gray-500 hover:text-gray-700"
          )}
        >
          Contexts
        </button>
        <button
          onClick={() => setViewMode("ai-generated")}
          className={cn(
            "relative rounded-md px-4 py-1.5 text-sm font-medium transition-colors",
            viewMode === "ai-generated"
              ? "bg-white text-gray-900 shadow-sm"
              : "text-gray-500 hover:text-gray-700"
          )}
        >
          AI Generated
          {aiContexts && aiContexts.length > 0 && (
            <span className="ml-1.5 inline-flex h-4 w-4 items-center justify-center rounded-full bg-violet-600 text-[10px] text-white">
              {aiContexts.length}
            </span>
          )}
        </button>
      </div>

      {/* Tab content */}
      {viewMode === "contexts" ? (
        <ContextTable />
      ) : (
        <div className="space-y-4">
          {/* Actions bar */}
          <div className="flex items-center justify-between">
            <button
              onClick={handleSanitize}
              disabled={isStreaming || !onSendChatMessage}
              className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-violet-700 disabled:opacity-50"
            >
              {isStreaming ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Sanitizing...
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" />
                  Sanitize All Contexts
                </>
              )}
            </button>

            {aiContexts && aiContexts.length > 0 && (
              <div className="flex items-center gap-2">
                {!allUploaded && (
                  <button
                    onClick={() => bulkUpload()}
                    disabled={someUploading || pendingCount === 0}
                    className="flex items-center gap-1.5 rounded-lg border border-violet-300 bg-violet-50 px-3 py-1.5 text-xs font-medium text-violet-700 transition-colors hover:bg-violet-100 disabled:opacity-50"
                  >
                    <Upload className="h-3.5 w-3.5" />
                    Upload All ({pendingCount})
                  </button>
                )}
                <button
                  onClick={dismissAiContexts}
                  className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700"
                >
                  <X className="h-3.5 w-3.5" />
                  Dismiss
                </button>
              </div>
            )}
          </div>

          {/* Token usage */}
          {sanitizeUsage && (
            <div className="flex items-center gap-4 rounded-lg bg-gray-50 px-4 py-2 text-xs text-gray-500">
              <span>
                Input: <strong className="text-gray-700">{sanitizeUsage.input_tokens.toLocaleString()}</strong> tokens
              </span>
              <span>
                Output: <strong className="text-gray-700">{sanitizeUsage.output_tokens.toLocaleString()}</strong> tokens
              </span>
            </div>
          )}

          {/* AI context list */}
          {aiContexts && aiContexts.length > 0 ? (
            <div className="rounded-lg border border-gray-200 bg-white">
              {/* Column headers */}
              <div className="grid grid-cols-[1fr_70px_100px_140px] gap-3 border-b border-gray-200 bg-gray-50 px-4 py-2">
                <span className="text-xs font-medium uppercase tracking-wider text-gray-500">
                  Name
                </span>
                <span className="text-xs font-medium uppercase tracking-wider text-gray-500">
                  Scope
                </span>
                <span className="text-xs font-medium uppercase tracking-wider text-gray-500">
                  Status
                </span>
                <span className="text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                  Actions
                </span>
              </div>

              {aiContexts.map((ctx) => (
                <AiContextRow key={ctx.id} ctx={ctx} />
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-gray-200 bg-white py-16 text-center">
              <Sparkles className="mx-auto mb-3 h-8 w-8 text-gray-300" />
              <p className="text-sm font-medium text-gray-500">No AI-generated contexts yet</p>
              <p className="mt-1 text-xs text-gray-400">
                Click &ldquo;Sanitize All Contexts&rdquo; to refactor your existing contexts
                using AI, or ask the chat assistant to help.
              </p>
            </div>
          )}

          {/* Edit AI context modal */}
          {editingAiCtx && <EditAiContextDialog ctx={editingAiCtx} />}
        </div>
      )}
    </div>
  );
}
