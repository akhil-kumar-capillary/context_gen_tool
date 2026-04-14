"use client";

import { useState, useCallback, useEffect } from "react";
import { Sparkles, Upload, X, Loader2, FileText } from "lucide-react";
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

type ActiveAction = "sanitize" | "summary" | null;

export function ContextPanel({ onSendChatMessage }: ContextPanelProps) {
  const [viewMode, setViewMode] = useState<ViewMode>("contexts");
  const [activeAction, setActiveAction] = useState<ActiveAction>(null);

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

  useEffect(() => {
    if (!isStreaming) setActiveAction(null);
  }, [isStreaming]);

  const handleSanitize = useCallback(() => {
    if (onSendChatMessage) {
      setViewMode("ai-generated");
      setActiveAction("sanitize");
      onSendChatMessage(
        "Please refactor and sanitize all my contexts using the blueprint. Restructure them into well-organized documents following best practices."
      );
    }
  }, [onSendChatMessage]);

  const handleAddSummary = useCallback(() => {
    if (onSendChatMessage) {
      setViewMode("ai-generated");
      setActiveAction("summary");
      onSendChatMessage(
        "Please add a concise summary to each of my context documents. " +
          "Generate a description under 300 characters and prepend it to the top of each context."
      );
    }
  }, [onSendChatMessage]);

  return (
    <div className="flex flex-col h-full gap-4">
      {/* Header */}
      <div className="shrink-0">
        <h1 className="text-xl font-semibold text-foreground">Context Management</h1>
        <p className="text-sm text-muted-foreground">
          Manage, create, and refactor context documents for your organization.
        </p>
      </div>

      {/* Tab toggle */}
      <div className="flex items-center rounded-lg border border-border bg-muted/50 p-0.5 w-fit shrink-0">
        <button
          onClick={() => setViewMode("contexts")}
          className={cn(
            "rounded-md px-4 py-1.5 text-sm font-medium transition-all",
            viewMode === "contexts"
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          Contexts
        </button>
        <button
          onClick={() => setViewMode("ai-generated")}
          className={cn(
            "relative rounded-md px-4 py-1.5 text-sm font-medium transition-all",
            viewMode === "ai-generated"
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          AI Generated
          {aiContexts && aiContexts.length > 0 && (
            <span className="ml-1.5 inline-flex h-4 w-4 items-center justify-center rounded-full bg-primary text-xs text-primary-foreground">
              {aiContexts.length}
            </span>
          )}
        </button>
      </div>

      {/* Tab content — fills remaining height */}
      {viewMode === "contexts" ? (
        <div className="flex-1 min-h-0 flex flex-col">
          <ContextTable />
        </div>
      ) : (
        <div className="space-y-4">
          {/* Actions bar */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <button
                onClick={handleSanitize}
                disabled={isStreaming || !onSendChatMessage}
                className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
              >
                {isStreaming && activeAction === "sanitize" ? (
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
              <button
                onClick={handleAddSummary}
                disabled={isStreaming || !onSendChatMessage}
                className="flex items-center gap-2 rounded-lg border border-primary/30 bg-primary/5 px-4 py-2 text-sm font-medium text-primary transition-colors hover:bg-primary/10 disabled:opacity-50"
              >
                {isStreaming && activeAction === "summary" ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Summarizing...
                  </>
                ) : (
                  <>
                    <FileText className="h-4 w-4" />
                    Add Summary in Context
                  </>
                )}
              </button>
            </div>

            {aiContexts && aiContexts.length > 0 && (
              <div className="flex items-center gap-2">
                {!allUploaded && (
                  <button
                    onClick={() => bulkUpload()}
                    disabled={someUploading || pendingCount === 0}
                    className="flex items-center gap-1.5 rounded-lg border border-primary/30 bg-primary/5 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/10 disabled:opacity-50"
                  >
                    <Upload className="h-3.5 w-3.5" />
                    Upload All ({pendingCount})
                  </button>
                )}
                <button
                  onClick={dismissAiContexts}
                  className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  <X className="h-3.5 w-3.5" />
                  Dismiss
                </button>
              </div>
            )}
          </div>

          {/* Token usage */}
          {sanitizeUsage && (
            <div className="flex items-center gap-4 rounded-lg bg-muted/50 px-4 py-2 text-xs text-muted-foreground">
              <span>
                Input: <strong className="text-foreground">{sanitizeUsage.input_tokens.toLocaleString()}</strong> tokens
              </span>
              <span>
                Output: <strong className="text-foreground">{sanitizeUsage.output_tokens.toLocaleString()}</strong> tokens
              </span>
            </div>
          )}

          {/* AI context list */}
          {aiContexts && aiContexts.length > 0 ? (
            <div className="rounded-lg border border-border bg-background">
              {/* Column headers */}
              <div className="grid grid-cols-[1fr_70px_100px_140px] gap-3 border-b border-border bg-muted/50 px-4 py-2">
                <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Name
                </span>
                <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Scope
                </span>
                <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Status
                </span>
                <span className="text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Actions
                </span>
              </div>

              {aiContexts.map((ctx) => (
                <AiContextRow key={ctx.id} ctx={ctx} />
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-border bg-background py-16 text-center">
              <Sparkles className="mx-auto mb-3 h-8 w-8 text-muted-foreground/50" />
              <p className="text-sm font-medium text-muted-foreground">No AI-generated contexts yet</p>
              <p className="mt-1 text-xs text-muted-foreground">
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
