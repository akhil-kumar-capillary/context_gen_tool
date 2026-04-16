"use client";

import { useCallback, useState } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import { UploadCloud, FileText, X, Loader2, AlertCircle, CheckCircle2, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import { useContextStore } from "@/stores/context-store";
import type { AiGeneratedContext } from "@/types";

const MAX_FILE_BYTES = 50 * 1024 * 1024;
const MAX_FILES = 20;

const ACCEPTED = {
  "application/pdf": [".pdf"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": [".pptx"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
  "text/html": [".html", ".htm"],
  "text/markdown": [".md", ".markdown", ".mdx"],
  "text/plain": [".txt", ".log", ".csv", ".tsv", ".yaml", ".yml", ".xml"],
  "application/json": [".json"],
  "image/png": [".png"],
  "image/jpeg": [".jpg", ".jpeg"],
  "image/tiff": [".tiff", ".tif"],
  "image/bmp": [".bmp"],
};

interface ConvertResponse {
  results: Array<{
    filename: string;
    suggested_name: string;
    content?: string;
    format?: string;
    status: "success" | "error";
    error?: string;
    tokens?: { input_tokens: number; output_tokens: number };
  }>;
  summary: { total: number; success: number; failed: number };
  supported_extensions: string[];
}

interface QueuedFile {
  file: File;
  id: string;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

interface UploadFilesTabProps {
  scope: "org" | "private";
  onScopeChange: (scope: "org" | "private") => void;
  onDone: () => void;
}

export function UploadFilesTab({ scope, onScopeChange, onDone }: UploadFilesTabProps) {
  const [queue, setQueue] = useState<QueuedFile[]>([]);
  const [refactor, setRefactor] = useState(true);
  const [converting, setConverting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const setAiContexts = useContextStore((s) => s.setAiContexts);

  const onDrop = useCallback((accepted: File[], rejected: FileRejection[]) => {
    setError(null);
    if (rejected.length > 0) {
      const first = rejected[0];
      const msg = first.errors[0]?.message || "File rejected";
      setError(`${first.file.name}: ${msg}`);
    }
    setQueue((prev) => {
      const existing = new Set(prev.map((q) => `${q.file.name}:${q.file.size}`));
      const additions = accepted
        .filter((f) => !existing.has(`${f.name}:${f.size}`))
        .map((f) => ({ file: f, id: `${f.name}-${f.size}-${Date.now()}-${Math.random()}` }));
      const next = [...prev, ...additions];
      if (next.length > MAX_FILES) {
        setError(`Max ${MAX_FILES} files per upload — extras dropped`);
        return next.slice(0, MAX_FILES);
      }
      return next;
    });
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED,
    maxSize: MAX_FILE_BYTES,
    multiple: true,
    disabled: converting,
  });

  const removeFile = (id: string) => {
    setQueue((prev) => prev.filter((q) => q.id !== id));
  };

  const handleConvert = async () => {
    if (queue.length === 0) {
      setError("Add at least one file");
      return;
    }
    const { token } = useAuthStore.getState();
    if (!token) {
      setError("Not authenticated");
      return;
    }

    setConverting(true);
    setError(null);
    setProgress(0);

    const form = new FormData();
    queue.forEach((q) => form.append("files", q.file, q.file.name));
    form.append("refactor", String(refactor));

    try {
      const res = await apiClient.postFormData<ConvertResponse>(
        "/api/contexts/convert-files",
        form,
        {
          token,
          onProgress: (p) => setProgress(p),
          timeoutMs: 600_000,
        }
      );

      // Turn each successful conversion into an AI-generated context so the
      // existing review/edit/bulk-upload UI can handle it.
      const aiContexts: AiGeneratedContext[] = res.results
        .filter((r) => r.status === "success" && r.content)
        .map((r, idx) => ({
          id: `upload-${Date.now()}-${idx}`,
          name: r.suggested_name,
          content: r.content || "",
          scope,
        }));

      const failed = res.results.filter((r) => r.status === "error");
      if (failed.length > 0) {
        const names = failed.map((f) => f.filename).join(", ");
        toast.error(`Failed to convert: ${names}`);
      }

      if (aiContexts.length === 0) {
        setError("No files converted successfully");
        setConverting(false);
        return;
      }

      setAiContexts(aiContexts);
      toast.success(
        `Converted ${aiContexts.length} file${aiContexts.length === 1 ? "" : "s"} — review and save`
      );
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
      setConverting(false);
    }
  };

  const totalBytes = queue.reduce((a, q) => a + q.file.size, 0);

  return (
    <div className="flex flex-1 flex-col min-h-0 gap-3">
      {/* Scope + Refactor row */}
      <div className="flex gap-3 shrink-0 items-end">
        <div className="w-40">
          <label className="mb-1 block text-xs font-medium text-foreground">Scope</label>
          <select
            value={scope}
            onChange={(e) => onScopeChange(e.target.value as "org" | "private")}
            className="w-full rounded-lg border border-input bg-background px-3 py-1.5 text-sm"
            disabled={converting}
          >
            <option value="org">Organization</option>
            <option value="private">Private</option>
          </select>
        </div>
        <label
          className={cn(
            "flex flex-1 items-center gap-2 rounded-lg border border-input bg-background px-3 py-1.5 text-sm cursor-pointer transition-colors",
            refactor && "border-primary/40 bg-primary/5",
            converting && "opacity-60 cursor-not-allowed"
          )}
        >
          <input
            type="checkbox"
            checked={refactor}
            onChange={(e) => setRefactor(e.target.checked)}
            disabled={converting}
            className="h-3.5 w-3.5 accent-primary"
          />
          <Sparkles className="h-3.5 w-3.5 text-primary" />
          <span className="flex-1 font-medium">LLM refactor</span>
          <span className="text-xs text-muted-foreground">cleaner output · slower</span>
        </label>
      </div>

      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={cn(
          "shrink-0 flex flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors cursor-pointer",
          isDragActive
            ? "border-primary bg-primary/5"
            : "border-border bg-muted/30 hover:bg-muted/50",
          converting && "pointer-events-none opacity-60"
        )}
      >
        <input {...getInputProps()} />
        <UploadCloud className="h-8 w-8 text-muted-foreground mb-2" />
        <p className="text-sm font-medium text-foreground">
          {isDragActive ? "Drop files to queue" : "Drag & drop files — or click to browse"}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          PDF, DOCX, PPTX, XLSX, HTML, MD, JSON, TXT, images · 50 MB per file · up to {MAX_FILES} files
        </p>
      </div>

      {/* Queued files list */}
      <div className="flex flex-1 flex-col min-h-0 rounded-lg border border-border bg-background overflow-hidden">
        <div className="flex items-center justify-between border-b border-border bg-muted/30 px-3 py-1.5 shrink-0">
          <span className="text-xs font-medium text-foreground">
            {queue.length === 0 ? "No files queued" : `${queue.length} file${queue.length === 1 ? "" : "s"} queued`}
          </span>
          {queue.length > 0 && (
            <span className="text-xs text-muted-foreground">{formatBytes(totalBytes)} total</span>
          )}
        </div>
        <div className="flex-1 overflow-y-auto">
          {queue.length === 0 ? (
            <div className="flex h-full items-center justify-center px-4 py-8 text-xs text-muted-foreground">
              Queued files appear here.
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {queue.map((q) => (
                <li key={q.id} className="flex items-center gap-3 px-3 py-2">
                  <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="flex-1 min-w-0">
                    <p className="truncate text-sm text-foreground">{q.file.name}</p>
                    <p className="text-xs text-muted-foreground">{formatBytes(q.file.size)}</p>
                  </div>
                  {!converting && (
                    <button
                      onClick={() => removeFile(q.id)}
                      className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                      aria-label={`Remove ${q.file.name}`}
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Progress bar — only during convert */}
      {converting && (
        <div className="shrink-0 space-y-1.5">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <Loader2 className="h-3 w-3 animate-spin" />
              {progress < 1 ? "Uploading..." : refactor ? "Converting + refactoring..." : "Converting..."}
            </span>
            <span>{Math.round(progress * 100)}%</span>
          </div>
          <div className="h-1 overflow-hidden rounded bg-muted">
            <div
              className="h-full bg-primary transition-all"
              style={{ width: `${Math.max(progress * 100, converting && progress >= 1 ? 100 : progress * 100)}%` }}
            />
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive shrink-0">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          {error}
        </div>
      )}

      {/* Convert button */}
      <div className="flex items-center justify-end gap-3 shrink-0">
        <button
          onClick={handleConvert}
          disabled={converting || queue.length === 0}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-60 disabled:pointer-events-none"
        >
          {converting ? (
            <span className="flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              Converting...
            </span>
          ) : (
            <span className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4" />
              Convert {queue.length > 0 ? `${queue.length} file${queue.length === 1 ? "" : "s"}` : ""}
            </span>
          )}
        </button>
      </div>
    </div>
  );
}
