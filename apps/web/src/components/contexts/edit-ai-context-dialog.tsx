"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { CONTEXT_NAME_REGEX, CONTEXT_NAME_ERROR } from "@/lib/utils";
import { useContextStore } from "@/stores/context-store";
import { RichTextEditor } from "@/components/shared/rich-text-editor";
import type { AiGeneratedContext } from "@/types";

interface EditAiContextDialogProps {
  ctx: AiGeneratedContext;
}

export function EditAiContextDialog({ ctx }: EditAiContextDialogProps) {
  const { updateAiContext, setEditingContextId } = useContextStore();

  const [name, setName] = useState(ctx.name);
  const [content, setContent] = useState(ctx.content);
  const [scope, setScope] = useState<"org" | "private">(ctx.scope);
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
      <div className="w-full max-w-2xl max-h-[85vh] flex flex-col rounded-xl bg-background shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4 shrink-0">
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
        <div className="flex-1 flex flex-col overflow-hidden px-6 py-5 gap-4 min-h-0">
          <div className="shrink-0">
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

          <div className="shrink-0">
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

          <div className="flex-1 flex flex-col min-h-0">
            <label className="mb-1.5 text-sm font-medium text-foreground shrink-0">Content</label>
            <RichTextEditor
              value={content}
              onChange={setContent}
              className="flex-1 min-h-0"
            />
          </div>

          {error && (
            <div className="rounded-lg border border-destructive/20 bg-destructive/5 px-4 py-2.5 text-sm text-destructive shrink-0">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 border-t border-border px-6 py-4 shrink-0">
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
