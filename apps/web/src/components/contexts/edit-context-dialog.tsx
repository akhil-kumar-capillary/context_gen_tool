"use client";

import { useState } from "react";
import { X, Loader2, AlertCircle } from "lucide-react";
import { motion } from "framer-motion";
import { CONTEXT_NAME_REGEX, CONTEXT_NAME_ERROR } from "@/lib/utils";
import { useContextStore } from "@/stores/context-store";
import { RichTextEditor } from "@/components/shared/rich-text-editor";
import type { Context } from "@/types";

interface EditContextDialogProps {
  ctx: Context;
}

export function EditContextDialog({ ctx }: EditContextDialogProps) {
  const { updateContext, setEditingContextId } = useContextStore();

  const [name, setName] = useState(ctx.name);
  const [content, setContent] = useState(ctx.context || "");
  const [scope, setScope] = useState<"org" | "private">(ctx.scope);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    if (!name.trim()) { setError("Name is required"); return; }
    if (!CONTEXT_NAME_REGEX.test(name)) { setError(CONTEXT_NAME_ERROR); return; }
    if (name.length > 100) { setError("Name must be 100 characters or less"); return; }
    if (!content.trim()) { setError("Content is required"); return; }

    setSaving(true);
    setError(null);
    try {
      await updateContext(ctx.id, name.trim(), content, scope);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex justify-end bg-black/30 backdrop-blur-[2px]">
      {/* Backdrop click to close */}
      <div className="flex-1" onClick={() => setEditingContextId(null)} />

      {/* Drawer */}
      <motion.div
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", stiffness: 300, damping: 30 }}
        className="flex w-full sm:w-3/4 lg:w-1/2 flex-col bg-background shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-base font-semibold text-foreground">Edit Context</h2>
          <button
            onClick={() => setEditingContextId(null)}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body — flex column so content area fills remaining height */}
        <div className="flex flex-1 flex-col overflow-hidden px-6 py-4 gap-3">
          {/* Name + Scope row (compact) */}
          <div className="flex gap-3 shrink-0">
            <div className="flex-1">
              <label htmlFor="edit-name" className="mb-1 block text-xs font-medium text-foreground">
                Name
              </label>
              <input
                id="edit-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={100}
                className="w-full rounded-lg border border-input bg-background px-3 py-1.5 text-sm transition-colors"
              />
            </div>
            <div className="w-36 shrink-0">
              <label htmlFor="edit-scope" className="mb-1 block text-xs font-medium text-foreground">
                Scope
              </label>
              <select
                id="edit-scope"
                value={scope}
                onChange={(e) => setScope(e.target.value as "org" | "private")}
                className="w-full rounded-lg border border-input bg-background px-3 py-1.5 text-sm transition-colors"
              >
                <option value="org">Organization</option>
                <option value="private">Private</option>
              </select>
            </div>
          </div>

          {/* Content — fills all remaining vertical space */}
          <div className="flex flex-1 flex-col min-h-0">
            <label className="mb-1.5 text-xs font-medium text-foreground shrink-0">Content</label>
            <RichTextEditor
              value={content}
              onChange={setContent}
              className="flex-1 min-h-0"
            />
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/5 px-4 py-2.5 text-sm text-destructive">
              <AlertCircle className="h-4 w-4 shrink-0" />
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
            disabled={saving}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-70 disabled:pointer-events-none"
          >
            {saving ? (
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                Saving...
              </span>
            ) : (
              "Save"
            )}
          </button>
        </div>
      </motion.div>
    </div>
  );
}
