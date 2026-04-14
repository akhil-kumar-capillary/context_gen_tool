"use client";

import { SafeHtml } from "@/components/shared/safe-html";

import { useState } from "react";
import { X } from "lucide-react";
import { cn, CONTEXT_NAME_REGEX, CONTEXT_NAME_ERROR } from "@/lib/utils";
import { useContextStore } from "@/stores/context-store";
import { MarkdownRenderer } from "@/components/chat/markdown-renderer";
import type { AiGeneratedContext } from "@/types";

function looksLikeHtml(text: string): boolean {
  return /^\s*<[a-z][\s\S]*>/i.test(text.trim());
}

interface EditAiContextDialogProps {
  ctx: AiGeneratedContext;
}

export function EditAiContextDialog({ ctx }: EditAiContextDialogProps) {
  const { updateAiContext, setEditingContextId } = useContextStore();

  const [name, setName] = useState(ctx.name);
  const [content, setContent] = useState(ctx.content);
  const [scope, setScope] = useState<"org" | "private">(ctx.scope);
  const [tab, setTab] = useState<"edit" | "preview">("edit");
  const [error, setError] = useState<string | null>(null);

  const handleSave = () => {
    if (!name.trim()) { setError("Name is required"); return; }
    if (!CONTEXT_NAME_REGEX.test(name)) { setError(CONTEXT_NAME_ERROR); return; }
    if (name.length > 100) { setError("Name must be 100 characters or less"); return; }
    if (!content.trim()) { setError("Content is required"); return; }

    updateAiContext(ctx.id, { name: name.trim(), content, scope });
    setEditingContextId(null);
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/30 backdrop-blur-[2px]">
      <div className="w-full max-w-2xl rounded-xl bg-background shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-base font-semibold text-foreground">Edit AI Context</h2>
          <button
            onClick={() => setEditingContextId(null)}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="space-y-4 px-6 py-5">
          <div>
            <label htmlFor="ai-name" className="mb-1.5 block text-sm font-medium text-foreground">Name</label>
            <input
              id="ai-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={100}
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm transition-colors"
            />
          </div>

          <div>
            <label htmlFor="ai-scope" className="mb-1.5 block text-sm font-medium text-foreground">Scope</label>
            <select
              id="ai-scope"
              value={scope}
              onChange={(e) => setScope(e.target.value as "org" | "private")}
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm transition-colors"
            >
              <option value="org">Organization</option>
              <option value="private">Private</option>
            </select>
          </div>

          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <label className="text-sm font-medium text-foreground">Content</label>
              <div className="flex rounded-lg border border-border bg-muted/50 p-0.5">
                <button
                  onClick={() => setTab("edit")}
                  className={cn(
                    "rounded-md px-3 py-1 text-xs font-medium transition-all",
                    tab === "edit" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  Edit
                </button>
                <button
                  onClick={() => setTab("preview")}
                  className={cn(
                    "rounded-md px-3 py-1 text-xs font-medium transition-all",
                    tab === "preview" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  Preview
                </button>
              </div>
            </div>

            {tab === "edit" ? (
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                className="h-72 w-full resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm font-mono transition-colors"
              />
            ) : (
              <div className="h-72 overflow-y-auto rounded-lg border border-border bg-muted/30 p-4 text-sm">
                {content ? (
                  looksLikeHtml(content) ? (
                    <SafeHtml html={content} className="prose prose-sm max-w-none text-foreground" />
                  ) : (
                    <MarkdownRenderer content={content} />
                  )
                ) : (
                  <p className="italic text-muted-foreground">Nothing to preview</p>
                )}
              </div>
            )}
          </div>

          {error && (
            <div className="rounded-lg border border-destructive/20 bg-destructive/5 px-4 py-2.5 text-sm text-destructive">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 border-t border-border px-6 py-4">
          <button
            onClick={() => setEditingContextId(null)}
            className="rounded-lg px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
