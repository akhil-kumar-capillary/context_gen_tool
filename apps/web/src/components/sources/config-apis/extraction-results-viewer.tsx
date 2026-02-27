"use client";

import { useEffect, useState } from "react";
import {
  ChevronDown, ChevronRight, Check, AlertCircle,
  Loader2, Clock, FileJson, FolderOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import {
  useConfigApisStore,
  type APICallResult,
} from "@/stores/config-apis-store";

// ── Category display names ──

const CATEGORY_LABELS: Record<string, string> = {
  loyalty: "Loyalty Programs",
  extended_fields: "Extended Fields",
  campaigns: "Campaigns & Messaging",
  promotions: "Promotions & Rewards",
  coupons: "Coupon Series",
  audiences: "Audiences & Segments",
  org_settings: "Org Settings",
};

// ── Component ──

export function ExtractionResultsViewer({ runId }: { runId: string }) {
  const { token } = useAuthStore();
  const {
    extractionCallLog,
    rawApiResponse,
    isLoadingCallLog,
    isLoadingRawResponse,
    setExtractionCallLog,
    setRawApiResponse,
    setIsLoadingCallLog,
    setIsLoadingRawResponse,
  } = useConfigApisStore();

  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());
  const [selectedApi, setSelectedApi] = useState<{ category: string; api: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load call log when runId changes
  useEffect(() => {
    if (!token || !runId) return;
    const load = async () => {
      setIsLoadingCallLog(true);
      setError(null);
      try {
        const data = await apiClient.get<{ call_log: Record<string, APICallResult[]> }>(
          `/api/sources/config-apis/extract/runs/${runId}/call-log`,
          { token }
        );
        setExtractionCallLog(data.call_log);
        // Auto-expand all categories
        setExpandedCategories(new Set(Object.keys(data.call_log)));
      } catch (e) {
        console.error("Failed to load call log:", e);
        setError(e instanceof Error ? e.message : "Failed to load call log");
        setExtractionCallLog(null);
      }
      setIsLoadingCallLog(false);
    };
    load();
  }, [token, runId, setExtractionCallLog, setIsLoadingCallLog]);

  // Load raw response when an API is selected
  useEffect(() => {
    if (!token || !runId || !selectedApi) return;
    const load = async () => {
      setIsLoadingRawResponse(true);
      try {
        const data = await apiClient.get<{ data: unknown }>(
          `/api/sources/config-apis/extract/runs/${runId}/raw/${selectedApi.category}/${selectedApi.api}`,
          { token }
        );
        setRawApiResponse(data.data);
      } catch (e) {
        console.error("Failed to load raw response:", e);
        setRawApiResponse({ _error: e instanceof Error ? e.message : "Failed to load" });
      }
      setIsLoadingRawResponse(false);
    };
    load();
  }, [token, runId, selectedApi, setRawApiResponse, setIsLoadingRawResponse]);

  const toggleCategory = (cat: string) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  const handleApiClick = (category: string, api: string) => {
    if (selectedApi?.category === category && selectedApi?.api === api) {
      // Clicking same API again — collapse
      setSelectedApi(null);
      setRawApiResponse(null);
    } else {
      setSelectedApi({ category, api });
    }
  };

  if (isLoadingCallLog) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading extraction results...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-4">
        <div className="flex items-center gap-2 text-sm text-red-600">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      </div>
    );
  }

  if (!extractionCallLog || Object.keys(extractionCallLog).length === 0) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <p className="text-sm text-gray-400">No call log available for this extraction.</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white">
      <div className="border-b border-gray-200 px-5 py-3">
        <h3 className="text-sm font-semibold text-gray-700">API Call Results</h3>
        <p className="text-xs text-gray-400">
          Click any API call to inspect the raw response
        </p>
      </div>

      <div className="divide-y divide-gray-100">
        {Object.entries(extractionCallLog).map(([category, calls]) => {
          const isExpanded = expandedCategories.has(category);
          const successCount = calls.filter((c) => c.status === "success").length;
          const errorCount = calls.filter((c) => c.status === "error").length;
          const totalMs = calls.reduce((s, c) => s + (c.duration_ms || 0), 0);

          return (
            <div key={category}>
              {/* Category header */}
              <button
                onClick={() => toggleCategory(category)}
                className="flex w-full items-center gap-3 px-5 py-3 text-left hover:bg-gray-50 transition-colors"
              >
                <FolderOpen className="h-4 w-4 shrink-0 text-violet-500" />
                <div className="flex-1 min-w-0">
                  <span className="text-sm font-medium text-gray-900">
                    {CATEGORY_LABELS[category] || category}
                  </span>
                  <div className="flex items-center gap-2 mt-0.5">
                    {successCount > 0 && (
                      <span className="text-[10px] font-medium text-green-600">
                        {successCount} OK
                      </span>
                    )}
                    {errorCount > 0 && (
                      <span className="text-[10px] font-medium text-red-600">
                        {errorCount} failed
                      </span>
                    )}
                    <span className="text-[10px] text-gray-400">
                      {(totalMs / 1000).toFixed(1)}s
                    </span>
                  </div>
                </div>
                {isExpanded ? (
                  <ChevronDown className="h-4 w-4 text-gray-400" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-gray-400" />
                )}
              </button>

              {/* API call rows */}
              {isExpanded && (
                <div className="bg-gray-50/50">
                  {calls.map((call, idx) => {
                    const isSelected =
                      selectedApi?.category === category &&
                      selectedApi?.api === call.api_name;
                    const isSuccess = call.status === "success";

                    return (
                      <div key={`${call.api_name}-${idx}`}>
                        <button
                          onClick={() => handleApiClick(category, call.api_name)}
                          className={cn(
                            "flex w-full items-center gap-3 pl-10 pr-5 py-2 text-left transition-colors text-xs",
                            isSelected
                              ? "bg-violet-50 border-l-2 border-violet-400"
                              : "hover:bg-gray-100 border-l-2 border-transparent"
                          )}
                        >
                          {/* Status icon */}
                          {isSuccess ? (
                            <Check className="h-3.5 w-3.5 shrink-0 text-green-500" />
                          ) : (
                            <AlertCircle className="h-3.5 w-3.5 shrink-0 text-red-500" />
                          )}

                          {/* API name */}
                          <span
                            className={cn(
                              "flex-1 font-mono text-xs truncate",
                              isSuccess ? "text-gray-700" : "text-red-600"
                            )}
                          >
                            {call.api_name}
                          </span>

                          {/* Item count */}
                          {isSuccess && call.item_count != null && (
                            <span className="text-[10px] text-gray-500 tabular-nums w-16 text-right">
                              {call.item_count} item{call.item_count !== 1 ? "s" : ""}
                            </span>
                          )}

                          {/* Error message (abbreviated) */}
                          {!isSuccess && call.error_message && (
                            <span className="text-[10px] text-red-500 truncate max-w-[200px]">
                              {call.error_message}
                            </span>
                          )}

                          {/* Duration */}
                          <span className="text-[10px] text-gray-400 tabular-nums w-14 text-right">
                            {call.duration_ms}ms
                          </span>

                          {/* HTTP status */}
                          {call.http_status != null && call.http_status > 0 && (
                            <span
                              className={cn(
                                "rounded px-1.5 py-0.5 text-[9px] font-medium tabular-nums",
                                call.http_status >= 200 && call.http_status < 300
                                  ? "bg-green-100 text-green-700"
                                  : call.http_status >= 400
                                  ? "bg-red-100 text-red-700"
                                  : "bg-yellow-100 text-yellow-700"
                              )}
                            >
                              {call.http_status}
                            </span>
                          )}

                          {/* Expand indicator */}
                          <FileJson
                            className={cn(
                              "h-3 w-3 shrink-0",
                              isSelected ? "text-violet-500" : "text-gray-300"
                            )}
                          />
                        </button>

                        {/* Raw JSON panel */}
                        {isSelected && (
                          <div className="border-t border-gray-200 bg-white">
                            <div className="px-10 py-3">
                              {isLoadingRawResponse ? (
                                <div className="flex items-center gap-2 text-xs text-gray-400">
                                  <Loader2 className="h-3 w-3 animate-spin" />
                                  Loading response...
                                </div>
                              ) : rawApiResponse != null ? (
                                <div className="relative">
                                  <div className="flex items-center justify-between mb-2">
                                    <span className="text-[10px] font-medium text-gray-500 uppercase tracking-wider">
                                      Raw Response
                                    </span>
                                    {call.response_bytes != null && (
                                      <span className="text-[10px] text-gray-400">
                                        {formatBytes(call.response_bytes)}
                                      </span>
                                    )}
                                  </div>
                                  <pre className="max-h-80 overflow-auto rounded-lg bg-gray-900 p-4 text-[11px] text-gray-200 leading-relaxed font-mono">
                                    {formatJson(rawApiResponse)}
                                  </pre>
                                </div>
                              ) : (
                                <p className="text-xs text-gray-400">No response data available.</p>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Helpers ──

function formatJson(data: unknown): string {
  try {
    const text = JSON.stringify(data, null, 2);
    // Cap display at 50K chars
    if (text.length > 50_000) {
      return text.slice(0, 50_000) + "\n... (truncated)";
    }
    return text;
  } catch {
    return String(data);
  }
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
