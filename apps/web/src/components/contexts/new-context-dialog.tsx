"use client";

import { useState } from "react";
import { X, Loader2, AlertCircle, PenLine, UploadCloud } from "lucide-react";
import { motion } from "framer-motion";
import { cn, CONTEXT_NAME_REGEX, CONTEXT_NAME_ERROR } from "@/lib/utils";
import { useContextStore } from "@/stores/context-store";
import { RichTextEditor } from "@/components/shared/rich-text-editor";
import { UploadFilesTab } from "./upload-files-tab";

type TabId = "write" | "upload";

export function NewContextDialog() {
  const { createContext, setIsCreating } = useContextStore();

  const [tab, setTab] = useState<TabId>("write");
  const [name, setName] = useState("");
  const [content, setContent] = useState("");
  const [scope, setScope] = useState<"org" | "private">("org");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCreate = async () => {
    if (!name.trim()) { setError("Name is required"); return; }
    if (!CONTEXT_NAME_REGEX.test(name)) { setError(CONTEXT_NAME_ERROR); return; }
    if (name.length > 100) { setError("Name must be 100 characters or less"); return; }
    if (!content.trim()) { setError("Content is required"); return; }

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
    <div className="fixed inset-0 z-[60] flex justify-end bg-black/30 backdrop-blur-[2px]">
      <div className="flex-1" onClick={() => setIsCreating(false)} />

      <motion.div
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", stiffness: 300, damping: 30 }}
        className="flex w-full sm:w-3/4 lg:w-1/2 flex-col bg-background shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-base font-semibold text-foreground">New Context</h2>
          <button
            onClick={() => setIsCreating(false)}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1 border-b border-border px-6 pt-3">
          <TabButton
            active={tab === "write"}
            onClick={() => setTab("write")}
            icon={<PenLine className="h-3.5 w-3.5" />}
            label="Write"
          />
          <TabButton
            active={tab === "upload"}
            onClick={() => setTab("upload")}
            icon={<UploadCloud className="h-3.5 w-3.5" />}
            label="Upload files"
          />
        </div>

        {/* Body */}
        <div className="flex flex-1 flex-col overflow-hidden px-6 py-4 gap-3">
          {tab === "write" ? (
            <>
              {/* Name + Scope row */}
              <div className="flex gap-3 shrink-0">
                <div className="flex-1">
                  <label htmlFor="new-name" className="mb-1 block text-xs font-medium text-foreground">
                    Name
                  </label>
                  <input
                    id="new-name"
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    maxLength={100}
                    placeholder="e.g. 01_MASTER_RULES"
                    className="w-full rounded-lg border border-input bg-background px-3 py-1.5 text-sm transition-colors"
                  />
                </div>
                <div className="w-36 shrink-0">
                  <label htmlFor="new-scope" className="mb-1 block text-xs font-medium text-foreground">
                    Scope
                  </label>
                  <select
                    id="new-scope"
                    value={scope}
                    onChange={(e) => setScope(e.target.value as "org" | "private")}
                    className="w-full rounded-lg border border-input bg-background px-3 py-1.5 text-sm transition-colors"
                  >
                    <option value="org">Organization</option>
                    <option value="private">Private</option>
                  </select>
                </div>
              </div>

              {/* Content */}
              <div className="flex flex-1 flex-col min-h-0">
                <label className="mb-1.5 text-xs font-medium text-foreground shrink-0">Content</label>
                <RichTextEditor
                  value={content}
                  onChange={setContent}
                  placeholder="Start writing your context..."
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
            </>
          ) : (
            <UploadFilesTab
              scope={scope}
              onScopeChange={setScope}
              onDone={() => setIsCreating(false)}
            />
          )}
        </div>

        {/* Footer — only shown for Write tab; Upload tab has its own convert button */}
        {tab === "write" && (
          <div className="flex items-center justify-end gap-3 border-t border-border px-6 py-4">
            <button
              onClick={() => setIsCreating(false)}
              className="rounded-lg px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              Cancel
            </button>
            <button
              onClick={handleCreate}
              disabled={saving}
              className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-70 disabled:pointer-events-none"
            >
              {saving ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Creating...
                </span>
              ) : (
                "Create"
              )}
            </button>
          </div>
        )}
      </motion.div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 rounded-t-md px-3 py-2 text-xs font-medium transition-colors border-b-2 -mb-px",
        active
          ? "border-primary text-foreground"
          : "border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/50"
      )}
    >
      {icon}
      {label}
    </button>
  );
}
