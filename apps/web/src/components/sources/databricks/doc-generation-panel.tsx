"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Loader2,
  Play,
  FileText,
  CheckCircle,
  XCircle,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import { useDatabricksStore, type ContextDoc } from "@/stores/databricks-store";

export function DocGenerationPanel() {
  const { token } = useAuthStore();
  const {
    activeAnalysisId,
    isGenerating,
    setIsGenerating,
    generationProgress,
    clearGenerationProgress,
    contextDocs,
    setContextDocs,
    isLoadingDocs,
    setIsLoadingDocs,
  } = useDatabricksStore();

  // Load existing docs for the active analysis
  useEffect(() => {
    if (!activeAnalysisId) return;

    const loadDocs = async () => {
      setIsLoadingDocs(true);
      try {
        const data = await apiClient.get<{ docs: ContextDoc[]; count: number }>(
          `/api/sources/databricks/llm/docs/${activeAnalysisId}`,
          { token: token || undefined }
        );
        setContextDocs(data.docs);
      } catch (err) {
        console.error("Failed to load docs:", err);
      } finally {
        setIsLoadingDocs(false);
      }
    };

    loadDocs();
  }, [activeAnalysisId, token, setContextDocs, setIsLoadingDocs]);

  const handleGenerate = useCallback(async () => {
    if (!activeAnalysisId || isGenerating) return;

    setIsGenerating(true);
    clearGenerationProgress();

    try {
      await apiClient.post(
        "/api/sources/databricks/llm/generate",
        {
          analysis_id: activeAnalysisId,
          provider: "anthropic",
          model: "claude-opus-4-6",
        },
        { token: token || undefined }
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Generation failed to start";
      setIsGenerating(false);
      console.error("Generation start failed:", msg);
    }
  }, [activeAnalysisId, isGenerating, token, setIsGenerating, clearGenerationProgress]);

  const handleCancelGeneration = useCallback(async () => {
    if (!activeAnalysisId) return;
    try {
      await apiClient.post(
        `/api/sources/databricks/llm/cancel/${activeAnalysisId}`,
        {},
        { token: token || undefined }
      );
    } catch {
      // Backend will also send ws event; just reset UI
    }
    setIsGenerating(false);
  }, [activeAnalysisId, token, setIsGenerating]);

  // Detect which docs are being generated from progress events
  const docProgress: Record<string, string> = {};
  for (const evt of generationProgress) {
    if (evt.doc_key) {
      docProgress[evt.doc_key] = evt.status || "started";
    }
  }

  const isComplete = generationProgress.some(
    (e) => e.phase === "complete" && e.status === "done"
  );

  // Reload docs when generation completes
  useEffect(() => {
    if (!isComplete || !activeAnalysisId) return;
    const reload = async () => {
      try {
        const data = await apiClient.get<{ docs: ContextDoc[]; count: number }>(
          `/api/sources/databricks/llm/docs/${activeAnalysisId}`,
          { token: token || undefined }
        );
        setContextDocs(data.docs);
      } catch (err) {
        console.error("Failed to reload docs:", err);
      }
    };
    reload();
  }, [isComplete, activeAnalysisId, token, setContextDocs]);

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <div className="mb-4 flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-violet-600" />
          <h2 className="text-lg font-semibold text-gray-900">Generate Context Documents</h2>
        </div>

        {!activeAnalysisId ? (
          <p className="text-sm text-gray-500">
            Select an analysis run first, or go back to the analysis step.
          </p>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-gray-600">
              Generate 5 context documents from the analysis results using LLM.
              This will create: Master Rules, Schema Reference, Business Mappings,
              Default Filters, and Query Patterns.
            </p>

            <div className="flex items-center gap-2">
              <button
                onClick={handleGenerate}
                disabled={isGenerating}
                className={cn(
                  "flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all",
                  isGenerating
                    ? "bg-gray-100 text-gray-400"
                    : "bg-violet-600 text-white hover:bg-violet-700 shadow-sm"
                )}
              >
                {isGenerating ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Generating...
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4" />
                    Generate Documents
                  </>
                )}
              </button>
              {isGenerating && (
                <button
                  onClick={handleCancelGeneration}
                  className="flex items-center gap-1.5 rounded-lg bg-[#eb6c6c] px-3 py-2 text-sm font-medium text-white shadow-sm transition-all hover:bg-[#d95b5b]"
                >
                  <XCircle className="h-4 w-4" />
                  Cancel
                </button>
              )}
            </div>

            {/* Per-doc progress */}
            {Object.keys(docProgress).length > 0 && (
              <div className="space-y-1">
                {Object.entries(docProgress).map(([key, status]) => (
                  <div key={key} className="flex items-center gap-2 text-sm">
                    {status === "done" ? (
                      <CheckCircle className="h-4 w-4 text-green-500" />
                    ) : status === "failed" ? (
                      <XCircle className="h-4 w-4 text-red-500" />
                    ) : (
                      <Loader2 className="h-4 w-4 animate-spin text-violet-600" />
                    )}
                    <span className="font-mono text-xs text-gray-600">{key}</span>
                    <span className="text-xs text-gray-400">{status}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Full progress log */}
            {generationProgress.length > 0 && (
              <div className="max-h-40 overflow-y-auto rounded-lg bg-gray-50 p-3">
                {generationProgress.slice(-15).map((evt, i) => (
                  <div key={i} className="text-xs text-gray-600">
                    <span className="font-mono text-gray-400">[{evt.phase}]</span>{" "}
                    {evt.doc_key && <span className="text-violet-600">{evt.doc_key} </span>}
                    {evt.status || ""}
                    {evt.word_count ? ` (${evt.word_count} words)` : ""}
                    {evt.error && <span className="text-red-500"> {evt.error}</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Generated Documents */}
      {contextDocs.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-900">
            <FileText className="h-4 w-4" />
            Generated Documents ({contextDocs.length})
          </h3>

          <div className="space-y-2">
            {contextDocs.map((doc) => (
              <DocCard key={doc.id} doc={doc} />
            ))}
          </div>
        </div>
      )}

      {isLoadingDocs && (
        <div className="flex items-center justify-center p-8">
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
        </div>
      )}
    </div>
  );
}

function DocCard({ doc }: { doc: ContextDoc }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="rounded-lg border border-gray-200 p-3">
      <div
        className="flex cursor-pointer items-center justify-between"
        onClick={() => setExpanded(!expanded)}
      >
        <div>
          <span className="text-sm font-medium text-gray-900">
            {doc.doc_key}
          </span>
          {doc.doc_name && (
            <span className="ml-2 text-xs text-gray-500">{doc.doc_name}</span>
          )}
        </div>
        <div className="flex items-center gap-2 text-xs text-gray-400">
          {doc.token_count && <span>~{doc.token_count} tokens</span>}
          {doc.model_used && <span>{doc.model_used.slice(0, 20)}</span>}
        </div>
      </div>

      {expanded && doc.doc_content && (
        <div className="mt-3 max-h-96 overflow-y-auto whitespace-pre-wrap rounded-lg bg-gray-50 p-4 text-xs text-gray-700">
          {doc.doc_content}
        </div>
      )}
    </div>
  );
}

