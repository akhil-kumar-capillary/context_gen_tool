"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { cn, CONTEXT_NAME_REGEX, CONTEXT_NAME_ERROR } from "@/lib/utils";
import { useContextStore } from "@/stores/context-store";
import { MarkdownRenderer } from "@/components/chat/markdown-renderer";

export function NewContextDialog() {
  const { createContext, setIsCreating } = useContextStore();

  const [name, setName] = useState("");
  const [content, setContent] = useState("");
  const [scope, setScope] = useState<"org" | "private">("org");
  const [tab, setTab] = useState<"edit" | "preview">("edit");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCreate = async () => {
    // Validate
    if (!name.trim()) {
      setError("Name is required");
      return;
    }
    if (!CONTEXT_NAME_REGEX.test(name)) {
      setError(CONTEXT_NAME_ERROR);
      return;
    }
    if (name.length > 100) {
      setError("Name must be 100 characters or less");
      return;
    }
    if (!content.trim()) {
      setError("Content is required");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await createContext(name.trim(), content, scope);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create");
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-3xl rounded-xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">New Context</h2>
          <button
            onClick={() => setIsCreating(false)}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="space-y-4 px-6 py-5">
          {/* Name */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={100}
              placeholder="e.g. 01_MASTER_RULES"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-100"
            />
            <p className="mt-1 text-xs text-gray-400">
              Letters, numbers, spaces, _ : # ( ) - , &middot; Max 100 chars
            </p>
          </div>

          {/* Scope */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Scope</label>
            <select
              value={scope}
              onChange={(e) => setScope(e.target.value as "org" | "private")}
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-100"
            >
              <option value="org">Organization</option>
              <option value="private">Private</option>
            </select>
          </div>

          {/* Content with edit/preview tabs */}
          <div>
            <div className="mb-1 flex items-center justify-between">
              <label className="text-sm font-medium text-gray-700">Content</label>
              <div className="flex gap-1 rounded-lg bg-gray-100 p-0.5">
                <button
                  onClick={() => setTab("edit")}
                  className={cn(
                    "rounded-md px-3 py-1 text-xs font-medium transition-colors",
                    tab === "edit"
                      ? "bg-white text-gray-900 shadow-sm"
                      : "text-gray-500 hover:text-gray-700"
                  )}
                >
                  Edit
                </button>
                <button
                  onClick={() => setTab("preview")}
                  className={cn(
                    "rounded-md px-3 py-1 text-xs font-medium transition-colors",
                    tab === "preview"
                      ? "bg-white text-gray-900 shadow-sm"
                      : "text-gray-500 hover:text-gray-700"
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
                placeholder="Enter context content (Markdown and HTML supported)..."
                className="h-72 w-full resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-100"
              />
            ) : (
              <div className="h-72 overflow-y-auto rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm">
                {content ? (
                  <MarkdownRenderer content={content} />
                ) : (
                  <p className="italic text-gray-400">Nothing to preview</p>
                )}
              </div>
            )}
          </div>

          {/* Error */}
          {error && (
            <div className="rounded-lg bg-red-50 px-4 py-2.5 text-sm text-red-600">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 border-t border-gray-200 px-6 py-4">
          <button
            onClick={() => setIsCreating(false)}
            className="rounded-lg px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100"
          >
            Cancel
          </button>
          <button
            onClick={handleCreate}
            disabled={saving}
            className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-violet-700 disabled:opacity-50"
          >
            {saving ? "Creating..." : "Create"}
          </button>
        </div>
      </div>
    </div>
  );
}
