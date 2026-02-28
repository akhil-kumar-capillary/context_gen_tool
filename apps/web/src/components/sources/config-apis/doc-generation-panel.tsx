"use client";

import { useEffect, useState } from "react";
import {
  Loader2, Play, Square, Check, AlertCircle, Clock, FileText, Copy, Trash2,
} from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import {
  useConfigApisStore,
  type ContextDoc,
} from "@/stores/config-apis-store";

export function DocGenerationPanel() {
  const { token, orgId } = useAuthStore();
  const {
    activeAnalysisId,
    contextDocs,
    generationProgress,
    isGenerating,
    isLoadingDocs,
    inclusions,
    customPrompts,
    setContextDocs,
    setIsGenerating,
    clearGenerationProgress,
    setActiveStep,
    setIsLoadingDocs,
  } = useConfigApisStore();

  const [expandedDoc, setExpandedDoc] = useState<number | null>(null);
  const [copied, setCopied] = useState<number | null>(null);

  // Load docs: by analysis ID if selected, otherwise all org docs
  useEffect(() => {
    if (!token) return;
    const load = async () => {
      setIsLoadingDocs(true);
      try {
        const url = activeAnalysisId
          ? `/api/sources/config-apis/llm/docs/${activeAnalysisId}`
          : `/api/sources/config-apis/llm/docs?org_id=${orgId}`;
        const data = await apiClient.get<{ docs: ContextDoc[] }>(url, { token });
        setContextDocs(data.docs);
      } catch {
        // ignore
      }
      setIsLoadingDocs(false);
    };
    load();
  }, [token, orgId, activeAnalysisId, setContextDocs, setIsLoadingDocs]);

  // Reload on generation completion
  const isComplete = generationProgress.some(
    (p) => p.phase === "complete" && p.status === "done"
  );

  useEffect(() => {
    if (!isComplete || !activeAnalysisId || !token) return;
    const reload = async () => {
      try {
        const data = await apiClient.get<{ docs: ContextDoc[] }>(
          `/api/sources/config-apis/llm/docs/${activeAnalysisId}`,
          { token }
        );
        setContextDocs(data.docs);
      } catch {
        // ignore
      }
    };
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isComplete, activeAnalysisId, token]);

  const handleGenerate = async () => {
    if (!token || !activeAnalysisId) return;

    clearGenerationProgress();
    setIsGenerating(true);

    try {
      // Build request with inclusions and custom prompts from the review step
      const body: Record<string, unknown> = { analysis_id: activeAnalysisId };
      if (Object.keys(inclusions).length > 0) {
        body.inclusions = inclusions;
      }
      if (Object.keys(customPrompts).length > 0) {
        body.system_prompts = customPrompts;
      }
      await apiClient.post(
        "/api/sources/config-apis/llm/generate",
        body,
        { token }
      );
    } catch (e) {
      console.error("Generation failed:", e);
      setIsGenerating(false);
    }
  };

  const handleCancel = async () => {
    if (!token || !activeAnalysisId) return;
    try {
      await apiClient.post(
        `/api/sources/config-apis/llm/cancel/${activeAnalysisId}`,
        {},
        { token }
      );
    } catch {
      // ignore
    }
  };

  const handleCopy = (docId: number, content: string) => {
    navigator.clipboard.writeText(content);
    setCopied(docId);
    setTimeout(() => setCopied(null), 2000);
  };

  const handleDeleteDoc = async (docId: number) => {
    if (!token) return;
    if (!confirm("Delete this generated document? This cannot be undone.")) return;
    try {
      await apiClient.delete(`/api/sources/config-apis/llm/doc/${docId}`, { token });
      setContextDocs(contextDocs.filter((d) => d.id !== docId));
    } catch (err) {
      console.error("Failed to delete doc:", err);
    }
  };

  return (
    <div className="space-y-4">
      {/* Action buttons + progress — only when an analysis is selected */}
      {activeAnalysisId && (
        <>
          <div className="flex items-center gap-3">
            {!isGenerating ? (
              <button
                onClick={handleGenerate}
                className="flex items-center gap-2 rounded-lg bg-violet-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-violet-700"
              >
                <Play className="h-4 w-4" />
                Generate Context Documents
              </button>
            ) : (
              <button
                onClick={handleCancel}
                className="flex items-center gap-2 rounded-lg bg-red-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-red-700"
              >
                <Square className="h-4 w-4" />
                Stop
              </button>
            )}
          </div>

          {/* Progress log */}
          {generationProgress.length > 0 && (
            <div className="rounded-xl border border-gray-200 bg-white">
              <div className="border-b border-gray-200 px-5 py-3">
                <h3 className="text-sm font-semibold text-gray-700">
                  Generation Progress
                  {isGenerating && <Loader2 className="ml-2 inline h-3.5 w-3.5 animate-spin" />}
                </h3>
              </div>
              <div className="max-h-48 overflow-y-auto p-4">
                {generationProgress.map((p, i) => (
                  <div
                    key={i}
                    className={cn(
                      "flex items-start gap-2 py-1 text-xs",
                      p.status === "failed" ? "text-red-600" : p.phase === "complete" ? "text-green-600" : "text-gray-600"
                    )}
                  >
                    {p.status === "done" || p.phase === "complete" ? (
                      <Check className="mt-0.5 h-3 w-3 shrink-0 text-green-500" />
                    ) : p.status === "failed" ? (
                      <AlertCircle className="mt-0.5 h-3 w-3 shrink-0 text-red-500" />
                    ) : (
                      <Clock className="mt-0.5 h-3 w-3 shrink-0 text-gray-400" />
                    )}
                    <span>{p.detail || p.error || p.phase || "..."}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Loading indicator */}
      {isLoadingDocs && (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
          <span className="ml-2 text-sm text-gray-400">Loading documents...</span>
        </div>
      )}

      {/* Generated docs */}
      {contextDocs.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-gray-700">
            Generated Documents ({contextDocs.length})
          </h3>
          {contextDocs.map((doc) => (
            <div
              key={doc.id}
              className="rounded-xl border border-gray-200 bg-white overflow-hidden"
            >
              <button
                onClick={() => setExpandedDoc(expandedDoc === doc.id ? null : doc.id)}
                className="flex w-full items-center justify-between px-5 py-3 text-left hover:bg-gray-50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <FileText className="h-4 w-4 text-violet-500" />
                  <div>
                    <p className="text-sm font-medium text-gray-900">
                      {doc.doc_name || doc.doc_key}
                    </p>
                    <p className="text-[11px] text-gray-400">
                      {doc.model_used} &middot; {doc.token_count?.toLocaleString() || "?"} tokens
                      &middot; {formatDate(doc.created_at || null)}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleCopy(doc.id, doc.doc_content || "");
                    }}
                    className="rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
                    title="Copy content"
                  >
                    {copied === doc.id ? (
                      <Check className="h-4 w-4 text-green-500" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteDoc(doc.id);
                    }}
                    className="rounded p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-500 transition-colors"
                    title="Delete document"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </button>
              {expandedDoc === doc.id && doc.doc_content && (
                <div className="border-t border-gray-200 bg-gray-50 p-5">
                  <pre className="whitespace-pre-wrap text-xs text-gray-700 font-mono max-h-96 overflow-y-auto">
                    {doc.doc_content}
                  </pre>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoadingDocs && contextDocs.length === 0 && !isGenerating && generationProgress.length === 0 && (
        <div className="rounded-xl border border-gray-200 bg-white px-6 py-12 text-center">
          <FileText className="mx-auto h-8 w-8 text-gray-300" />
          <p className="mt-2 text-sm text-gray-400">
            No documents generated yet. Click &quot;Generate&quot; to create context documents.
          </p>
        </div>
      )}
    </div>
  );
}
