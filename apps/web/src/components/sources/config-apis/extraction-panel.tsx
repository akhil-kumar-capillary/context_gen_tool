"use client";

import { useEffect, useRef, useState } from "react";
import {
  Loader2, Play, Square, ChevronDown, ChevronRight,
  RefreshCw, Check, AlertCircle, Clock, Trash2,
} from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import {
  useConfigApisStore,
  type CategorySchema,
  type ExtractionRun,
} from "@/stores/config-apis-store";
import { ExtractionResultsViewer } from "./extraction-results-viewer";

export function ExtractionPanel() {
  const { token, orgId, orgName } = useAuthStore();
  const {
    categories,
    selectedCategories,
    categoryParams,
    extractionRuns,
    extractionProgress,
    isExtracting,
    activeExtractionId,
    isLoadingRuns,
    setCategories,
    setSelectedCategories,
    toggleCategory,
    setCategoryParam,
    setExtractionRuns,
    setActiveExtractionId,
    setIsExtracting,
    clearExtractionProgress,
    setActiveStep,
    setIsLoadingRuns,
  } = useConfigApisStore();

  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  // Derive extraction-complete flag (used by re-fetch effect and JSX)
  const isComplete = extractionProgress.some(
    (p) => p.phase === "complete" && p.status === "done"
  );
  const hasReloadedRef = useRef(false);

  // Load categories on mount
  useEffect(() => {
    if (!token || categories.length > 0) return;
    const load = async () => {
      try {
        const data = await apiClient.get<{ categories: CategorySchema[] }>(
          "/api/sources/config-apis/categories",
          { token }
        );
        setCategories(data.categories);
      } catch (e) {
        console.error("Failed to load categories:", e);
      }
    };
    load();
  }, [token, categories.length, setCategories]);

  // Load extraction history on mount
  useEffect(() => {
    if (!token) return;
    const load = async () => {
      setIsLoadingRuns(true);
      try {
        const data = await apiClient.get<{ runs: ExtractionRun[] }>(
          `/api/sources/config-apis/extract/runs${orgId ? `?org_id=${orgId}` : ""}`,
          { token }
        );
        setExtractionRuns(data.runs);
      } catch (e) {
        console.error("Failed to load extraction runs:", e);
      }
      setIsLoadingRuns(false);
    };
    load();
  }, [token, orgId, setExtractionRuns, setIsLoadingRuns]);

  // Re-fetch extraction runs when an extraction completes (once per completion)
  useEffect(() => {
    if (!isComplete || !token || hasReloadedRef.current) return;
    hasReloadedRef.current = true;
    let cancelled = false;
    const reload = async () => {
      try {
        const data = await apiClient.get<{ runs: ExtractionRun[] }>(
          `/api/sources/config-apis/extract/runs${orgId ? `?org_id=${orgId}` : ""}`,
          { token }
        );
        if (!cancelled) setExtractionRuns(data.runs);
      } catch (e) {
        console.error("Failed to reload extraction runs:", e);
      }
    };
    reload();
    return () => { cancelled = true; };
  }, [isComplete, token, orgId, setExtractionRuns]);

  // Reset reload flag when a new extraction starts
  useEffect(() => {
    if (isExtracting) {
      hasReloadedRef.current = false;
    }
  }, [isExtracting]);

  // Get host from base_url in auth store
  const getHost = () => {
    // The user's base_url is set on auth. We need the host part.
    const baseUrl = useAuthStore.getState().baseUrl;
    if (baseUrl) {
      try {
        return new URL(baseUrl).host;
      } catch {
        return baseUrl.replace(/^https?:\/\//, "").replace(/\/$/, "");
      }
    }
    return "";
  };

  const handleStart = async () => {
    if (!token || !orgId || selectedCategories.length === 0) return;

    const host = getHost();
    if (!host) {
      setError("Unable to determine platform host from your session.");
      return;
    }

    setError(null);
    clearExtractionProgress();
    setIsExtracting(true);

    try {
      const data = await apiClient.post<{ run_id: string }>(
        "/api/sources/config-apis/extract/start",
        {
          host,
          org_id: orgId,
          categories: selectedCategories,
          category_params: categoryParams,
        },
        { token }
      );
      setActiveExtractionId(data.run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start extraction");
      setIsExtracting(false);
    }
  };

  const handleCancel = async () => {
    if (!token || !activeExtractionId) return;
    try {
      await apiClient.post(
        `/api/sources/config-apis/extract/cancel/${activeExtractionId}`,
        {},
        { token }
      );
    } catch {
      // ignore
    }
  };

  const toggleExpand = (catId: string) => {
    setExpandedCats((prev) => {
      const next = new Set(prev);
      if (next.has(catId)) next.delete(catId);
      else next.add(catId);
      return next;
    });
  };

  const handleDeleteExtraction = async (runId: string) => {
    if (!confirm("Delete this extraction run and all associated data?")) return;
    try {
      await apiClient.delete(`/api/sources/config-apis/extract/runs/${runId}`, {
        token: token || undefined,
      });
      setExtractionRuns(extractionRuns.filter((r) => r.id !== runId));
      if (activeExtractionId === runId) {
        setActiveExtractionId(null);
      }
    } catch (err) {
      console.error("Failed to delete extraction run:", err);
    }
  };

  return (
    <div className="space-y-4">
      {/* Category Picker */}
      <div className="rounded-xl border border-border bg-background">
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <div>
            <h3 className="text-sm font-semibold text-foreground">API Categories</h3>
            <p className="text-xs text-muted-foreground">
              Select which configuration data to extract{orgName ? ` for ${orgName}` : ""}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSelectedCategories(categories.map((c) => c.id))}
              className="text-xs text-primary hover:text-primary"
            >
              Select all
            </button>
            <span className="text-muted-foreground/50">|</span>
            <button
              onClick={() => setSelectedCategories([])}
              className="text-xs text-muted-foreground hover:text-muted-foreground"
            >
              Clear
            </button>
          </div>
        </div>

        <div className="divide-y divide-border">
          {categories.map((cat) => {
            const isSelected = selectedCategories.includes(cat.id);
            const isExpanded = expandedCats.has(cat.id);
            const hasParams = cat.params_schema.length > 0;

            return (
              <div key={cat.id}>
                <div className="flex items-center gap-3 px-5 py-3">
                  {/* Checkbox */}
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggleCategory(cat.id)}
                    className="h-4 w-4 rounded border-input text-primary focus:ring-primary"
                  />
                  {/* Label */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground">{cat.label}</p>
                    <p className="text-xs text-muted-foreground">{cat.description}</p>
                  </div>
                  {/* Expand params */}
                  {hasParams && (
                    <button
                      onClick={() => toggleExpand(cat.id)}
                      className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-muted-foreground"
                    >
                      {isExpanded ? (
                        <ChevronDown className="h-4 w-4" />
                      ) : (
                        <ChevronRight className="h-4 w-4" />
                      )}
                    </button>
                  )}
                </div>

                {/* Params */}
                {hasParams && isExpanded && (
                  <div className="border-t border-border bg-muted/50 px-5 py-3 pl-12">
                    <div className="flex flex-wrap gap-3">
                      {cat.params_schema.map((param) => (
                        <ParamInput
                          key={param.key}
                          param={param}
                          value={categoryParams[cat.id]?.[param.key]}
                          onChange={(val) => setCategoryParam(cat.id, param.key, val)}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600 flex items-center gap-2">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex items-center gap-3">
        {!isExtracting ? (
          <button
            onClick={handleStart}
            disabled={selectedCategories.length === 0 || !orgId}
            className="flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            <Play className="h-4 w-4" />
            Start Extraction ({selectedCategories.length} categories)
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

        {isComplete && (
          <button
            onClick={() => setActiveStep("analyze")}
            className="flex items-center gap-2 rounded-lg border border-primary/30 bg-primary/5 px-5 py-2.5 text-sm font-medium text-primary hover:bg-primary/10"
          >
            Continue to Analysis
            <ChevronRight className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Progress log */}
      {extractionProgress.length > 0 && (
        <div className="rounded-xl border border-border bg-background">
          <div className="border-b border-border px-5 py-3">
            <h3 className="text-sm font-semibold text-foreground">
              Progress
              {isExtracting && <Loader2 className="ml-2 inline h-3.5 w-3.5 animate-spin" />}
            </h3>
          </div>
          <div className="max-h-64 overflow-y-auto p-4">
            {extractionProgress.map((p, i) => (
              <div
                key={i}
                className={cn(
                  "flex items-start gap-2 py-1 text-xs",
                  p.status === "failed" || p.phase === "error"
                    ? "text-red-600"
                    : p.phase === "complete"
                    ? "text-green-600"
                    : "text-muted-foreground"
                )}
              >
                {p.status === "done" || p.phase === "complete" ? (
                  <Check className="mt-0.5 h-3 w-3 shrink-0 text-green-500" />
                ) : p.status === "failed" || p.phase === "error" ? (
                  <AlertCircle className="mt-0.5 h-3 w-3 shrink-0 text-red-500" />
                ) : (
                  <Clock className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" />
                )}
                <span>{p.detail || p.error || p.phase || "..."}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* API Call Results Viewer — shown after extraction completes or when viewing a past run */}
      {activeExtractionId && !isExtracting && (
        <ExtractionResultsViewer runId={activeExtractionId} />
      )}

      {/* Extraction History */}
      {(isLoadingRuns || extractionRuns.length > 0) && (
        <div className="rounded-xl border border-border bg-background">
          <div className="flex items-center justify-between border-b border-border px-5 py-3">
            <h3 className="text-sm font-semibold text-foreground">Extraction History</h3>
            {isLoadingRuns && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
          </div>
          {isLoadingRuns && extractionRuns.length === 0 ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              <span className="ml-2 text-xs text-muted-foreground">Loading history...</span>
            </div>
          ) : (
            <div className="divide-y divide-border">
              {extractionRuns.slice(0, 10).map((run) => (
                <div
                  key={run.id}
                  onClick={() => {
                    setActiveExtractionId(run.id);
                    setActiveStep("analyze");
                  }}
                  className={cn(
                    "flex w-full items-center justify-between px-5 py-3 text-left hover:bg-muted/50 transition-colors cursor-pointer",
                    activeExtractionId === run.id && "bg-primary/5"
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-foreground">
                        {run.categories?.length || 0} categories
                      </span>
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-xs font-medium",
                          run.status === "completed"
                            ? "bg-green-100 text-green-700"
                            : run.status === "failed"
                            ? "bg-red-100 text-red-700"
                            : "bg-yellow-100 text-yellow-700"
                        )}
                      >
                        {run.status}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {formatDate(run.created_at || null)} &middot; {run.host}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteExtraction(run.id);
                      }}
                      className="rounded p-1 text-muted-foreground hover:bg-red-50 hover:text-red-500 transition-colors"
                      title="Delete extraction run"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                    <ChevronRight className="h-4 w-4 text-muted-foreground/50" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Param Input ──

function ParamInput({
  param,
  value,
  onChange,
}: {
  param: CategorySchema["params_schema"][0];
  value: unknown;
  onChange: (val: unknown) => void;
}) {
  const resolvedValue = value ?? param.default ?? "";

  if (param.type === "boolean") {
    return (
      <label className="flex items-center gap-2 text-xs">
        <input
          type="checkbox"
          checked={!!resolvedValue}
          onChange={(e) => onChange(e.target.checked)}
          className="h-3.5 w-3.5 rounded border-input text-primary"
        />
        <span className="text-muted-foreground">{param.label}</span>
      </label>
    );
  }

  if (param.type === "select") {
    return (
      <div>
        <label className="mb-1 block text-xs font-medium text-muted-foreground">
          {param.label}
        </label>
        <select
          value={String(resolvedValue)}
          onChange={(e) => onChange(e.target.value)}
          className="rounded-md border border-input px-2 py-1.5 text-xs focus:border-primary/50 focus:outline-none"
        >
          {param.options?.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </div>
    );
  }

  if (param.type === "multi_select") {
    const selected = Array.isArray(resolvedValue) ? resolvedValue : [];
    return (
      <div>
        <label className="mb-1 block text-xs font-medium text-muted-foreground">
          {param.label}
        </label>
        <div className="flex flex-wrap gap-1.5">
          {param.options?.map((opt) => (
            <button
              key={opt}
              onClick={() => {
                if (selected.includes(opt)) {
                  onChange(selected.filter((v: string) => v !== opt));
                } else {
                  onChange([...selected, opt]);
                }
              }}
              className={cn(
                "rounded-full px-2.5 py-1 text-xs font-medium border transition-colors",
                selected.includes(opt)
                  ? "bg-primary/10 border-primary/30 text-primary"
                  : "bg-background border-border text-muted-foreground hover:border-input"
              )}
            >
              {opt}
            </button>
          ))}
        </div>
      </div>
    );
  }

  // number or text
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-muted-foreground">
        {param.label}
      </label>
      <input
        type={param.type === "number" ? "number" : "text"}
        value={String(resolvedValue)}
        placeholder={param.help}
        onChange={(e) =>
          onChange(param.type === "number" ? Number(e.target.value) || "" : e.target.value)
        }
        className="w-40 rounded-md border border-input px-2 py-1.5 text-xs focus:border-primary/50 focus:outline-none"
      />
    </div>
  );
}
