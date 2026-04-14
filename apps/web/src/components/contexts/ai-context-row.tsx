"use client";

import { memo } from "react";
import { Upload, Pencil, X, Check, Loader2, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { truncate } from "@/lib/text-utils";
import { useContextStore } from "@/stores/context-store";
import { ScopeBadge } from "./scope-badge";
import type { AiGeneratedContext } from "@/types";

interface AiContextRowProps {
  ctx: AiGeneratedContext;
}

export const AiContextRow = memo(function AiContextRow({ ctx }: AiContextRowProps) {
  const { updateAiContext, removeAiContext, uploadSingleAiContext, setEditingContextId } =
    useContextStore();

  const handleToggleScope = () => {
    updateAiContext(ctx.id, {
      scope: ctx.scope === "org" ? "private" : "org",
    });
  };

  const status = ctx.uploadStatus || "pending";
  const isUploading = status === "uploading";
  const isUploaded = status === "success";

  return (
    <div className="border-b border-border last:border-0">
      <div className="grid grid-cols-[1fr_70px_100px_140px] items-center gap-3 px-4 py-3">
        {/* Name + preview */}
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-foreground">{ctx.name}</p>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">
            {truncate(ctx.content, 80)}
          </p>
        </div>

        {/* Scope (clickable toggle) */}
        <ScopeBadge scope={ctx.scope} onClick={isUploaded ? undefined : handleToggleScope} />

        {/* Upload status */}
        <div className="flex items-center gap-1">
          {status === "pending" && (
            <span className="text-xs text-muted-foreground">Ready</span>
          )}
          {status === "uploading" && (
            <span className="flex items-center gap-1 text-xs text-primary">
              <Loader2 className="h-3 w-3 animate-spin" />
              Uploading...
            </span>
          )}
          {status === "success" && (
            <span className="flex items-center gap-1 text-xs text-green-600">
              <Check className="h-3 w-3" />
              Uploaded
            </span>
          )}
          {status === "error" && (
            <span className="flex items-center gap-1 text-xs text-red-500" title={ctx.error}>
              <AlertCircle className="h-3 w-3" />
              Failed
            </span>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-1">
          {!isUploaded && (
            <>
              <button
                onClick={() => uploadSingleAiContext(ctx)}
                disabled={isUploading}
                className={cn(
                  "rounded-md p-1.5 transition-colors",
                  isUploading
                    ? "text-muted-foreground/50"
                    : "text-primary hover:bg-primary/5 hover:text-primary"
                )}
                title="Upload"
              >
                <Upload className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => setEditingContextId(ctx.id)}
                disabled={isUploading}
                className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-muted-foreground disabled:text-muted-foreground/50"
                title="Edit"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => removeAiContext(ctx.id)}
                disabled={isUploading}
                className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-red-50 hover:text-red-500 disabled:text-muted-foreground/50"
                title="Remove"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
});
