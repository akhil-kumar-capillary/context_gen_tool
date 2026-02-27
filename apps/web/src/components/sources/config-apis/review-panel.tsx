"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useConfigApisStore } from "@/stores/config-apis-store";
import { useAuthStore } from "@/stores/auth-store";
import { InclusionPanel } from "./inclusion-panel";
import { PayloadPreview } from "./payload-preview";
import { AnalysisDashboard } from "./analysis-dashboard";
import {
  ListChecks, FileCode, FileJson, ChevronRight, Loader2, ArrowRight,
} from "lucide-react";
import { cn } from "@/lib/utils";

const DOC_TABS: { key: string; label: string; shortLabel: string }[] = [
  { key: "01_LOYALTY_MASTER", label: "Loyalty Programs", shortLabel: "Loyalty" },
  { key: "02_CAMPAIGN_REFERENCE", label: "Campaigns & Messaging", shortLabel: "Campaigns" },
  { key: "03_PROMOTION_RULES", label: "Promotions & Rewards", shortLabel: "Promotions" },
  { key: "04_AUDIENCE_SEGMENTS", label: "Audiences & Segments", shortLabel: "Audiences" },
  { key: "05_CUSTOMIZATIONS", label: "Fields & Settings", shortLabel: "Fields" },
];

type ControlMode = "inclusions" | "prompt" | "preview";

export function ReviewPanel() {
  const {
    activeAnalysisId,
    clusters,
    counters,
    entityTypeCounts,
    inclusions,
    customPrompts,
    defaultPrompts,
    payloadPreviews,
    isLoadingReviewData,
    isLoadingPayloads,
    setClusters,
    setCounters,
    setEntityTypeCounts,
    setDefaultPrompts,
    setTokenBudgets,
    setDocNames,
    setPayloadPreviews,
    setCustomPrompt,
    setIsLoadingReviewData,
    setIsLoadingPayloads,
    setActiveStep,
  } = useConfigApisStore();

  const { token } = useAuthStore();

  const [activeTab, setActiveTab] = useState(DOC_TABS[0].key);
  const [controlMode, setControlMode] = useState<ControlMode>("inclusions");
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  // ── Load review data on mount ──
  useEffect(() => {
    if (!activeAnalysisId || !token) return;

    const fetchData = async () => {
      setIsLoadingReviewData(true);
      try {
        const headers = {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        };

        const [clustersRes, countersRes, promptsRes] = await Promise.all([
          fetch(`/api/sources/config-apis/review/clusters/${activeAnalysisId}`, { headers }),
          fetch(`/api/sources/config-apis/review/counters/${activeAnalysisId}`, { headers }),
          fetch(`/api/sources/config-apis/review/default-prompts`, { headers }),
        ]);

        if (clustersRes.ok) {
          const data = await clustersRes.json();
          setClusters(data.clusters || []);
          setEntityTypeCounts(data.entity_type_counts || {});
        }
        if (countersRes.ok) {
          const data = await countersRes.json();
          setCounters(data.counters || {});
        }
        if (promptsRes.ok) {
          const data = await promptsRes.json();
          setDefaultPrompts(data.prompts || {});
          setTokenBudgets(data.budgets || {});
          setDocNames(data.doc_names || {});
        }

        // Initial payload preview
        await fetchPayloads();
      } catch (err) {
        console.error("Failed to load review data:", err);
      } finally {
        setIsLoadingReviewData(false);
      }
    };

    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeAnalysisId, token]);

  // ── Fetch payload previews ──
  const fetchPayloads = useCallback(async () => {
    if (!activeAnalysisId || !token) return;

    setIsLoadingPayloads(true);
    try {
      const hasInclusions = Object.keys(inclusions).length > 0;
      const res = await fetch("/api/sources/config-apis/review/preview-payload", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          analysis_id: activeAnalysisId,
          inclusions: hasInclusions ? inclusions : null,
          include_stats: true,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setPayloadPreviews(data.payloads || null);
      }
    } catch (err) {
      console.error("Failed to fetch payload preview:", err);
    } finally {
      setIsLoadingPayloads(false);
    }
  }, [activeAnalysisId, token, inclusions, setIsLoadingPayloads, setPayloadPreviews]);

  // ── Debounced refresh on inclusion changes ──
  useEffect(() => {
    if (!clusters) return; // Don't refresh before initial load
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchPayloads();
    }, 500);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [inclusions, fetchPayloads, clusters]);

  // ── No analysis selected ──
  if (!activeAnalysisId) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-8 text-center text-sm text-gray-500">
        Run analysis first to review and select items for LLM generation.
      </div>
    );
  }

  // ── Loading ──
  if (isLoadingReviewData) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-8 flex items-center justify-center gap-2 text-sm text-gray-500">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading review data...
      </div>
    );
  }

  // ── Total size summary ──
  const totalChars = payloadPreviews
    ? Object.values(payloadPreviews).reduce((s, p) => s + p.chars, 0)
    : 0;
  const totalTokens = payloadPreviews
    ? Object.values(payloadPreviews).reduce((s, p) => s + p.est_tokens, 0)
    : 0;

  return (
    <div className="space-y-4">
      {/* Entity overview dashboard */}
      {entityTypeCounts && Object.keys(entityTypeCounts).length > 0 && (
        <AnalysisDashboard />
      )}

      {/* Review & Select card */}
      <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
        {/* Doc tabs */}
        <div className="flex border-b border-gray-200 bg-gray-50 overflow-x-auto">
          {DOC_TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                "px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors",
                activeTab === tab.key
                  ? "border-violet-500 text-violet-700 bg-white"
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-100"
              )}
            >
              {tab.shortLabel}
            </button>
          ))}
        </div>

        {/* Control mode switcher */}
        <div className="flex items-center gap-1 px-4 py-2 border-b border-gray-100">
          {[
            { mode: "inclusions" as ControlMode, icon: ListChecks, label: "Inclusions" },
            { mode: "prompt" as ControlMode, icon: FileCode, label: "System Prompt" },
            { mode: "preview" as ControlMode, icon: FileJson, label: "Payload Preview" },
          ].map(({ mode, icon: Icon, label }) => (
            <button
              key={mode}
              onClick={() => setControlMode(mode)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
                controlMode === mode
                  ? "bg-violet-100 text-violet-700"
                  : "text-gray-500 hover:bg-gray-100"
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </button>
          ))}
        </div>

        {/* Content area — split pane for inclusions, full for prompt/preview */}
        <div className="flex" style={{ height: "500px" }}>
          {controlMode === "inclusions" && (
            <>
              {/* Left: inclusion toggles */}
              <div className="w-1/2 border-r border-gray-200 overflow-auto p-3">
                <InclusionPanel docKey={activeTab} />
              </div>
              {/* Right: payload preview */}
              <div className="w-1/2 overflow-hidden">
                <PayloadPreview docKey={activeTab} />
              </div>
            </>
          )}

          {controlMode === "prompt" && (
            <div className="flex-1 p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-700">
                  System Prompt for {DOC_TABS.find((t) => t.key === activeTab)?.label}
                </span>
                {customPrompts[activeTab] && (
                  <button
                    onClick={() => {
                      const store = useConfigApisStore.getState();
                      store.resetPrompt(activeTab);
                    }}
                    className="text-xs text-violet-600 hover:text-violet-800"
                  >
                    Reset to default
                  </button>
                )}
              </div>
              <textarea
                className="w-full h-[420px] p-3 border border-gray-200 rounded-lg text-xs font-mono text-gray-700 resize-none focus:outline-none focus:ring-2 focus:ring-violet-300"
                value={customPrompts[activeTab] || defaultPrompts[activeTab] || ""}
                onChange={(e) => setCustomPrompt(activeTab, e.target.value)}
                placeholder="System prompt will appear here..."
              />
            </div>
          )}

          {controlMode === "preview" && (
            <div className="flex-1 overflow-hidden">
              <PayloadPreview docKey={activeTab} />
            </div>
          )}
        </div>

        {/* Footer: size summary + continue button */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 bg-gray-50">
          <div className="flex items-center gap-4 text-xs text-gray-500">
            <span>
              Total: {totalChars.toLocaleString()} chars /
              ~{totalTokens.toLocaleString()} tokens across {
                payloadPreviews ? Object.keys(payloadPreviews).length : 0
              } docs
            </span>
          </div>

          <button
            onClick={() => setActiveStep("generate")}
            className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-white text-sm font-medium rounded-lg hover:bg-violet-700 transition-colors"
          >
            Continue to Generate
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
