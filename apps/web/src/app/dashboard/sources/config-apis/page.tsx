"use client";

import { useState, useCallback, useEffect } from "react";
import { useAuthStore } from "@/stores/auth-store";
import {
  Database, Loader2, RefreshCw, Download, Check, AlertCircle,
  ChevronRight, BarChart3, Megaphone, Users, Ticket, Star, Coins,
} from "lucide-react";
import { cn, formatDate } from "@/lib/utils";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ── Types ──────────────────────────────────────────────────────────── */

interface ApiType {
  id: string;
  label: string;
  description: string;
}

interface FetchResult {
  run_id: string;
  api_type: string;
  label: string;
  record_count: number;
  summary: string;
  data: unknown;
}

interface Extraction {
  id: string;
  api_type: string;
  label: string;
  status: string;
  created_at: string | null;
}

type ActiveTab = "fetch" | "history";

/* ── Icon lookup ────────────────────────────────────────────────────── */

const API_ICONS: Record<string, typeof Database> = {
  campaigns: Megaphone,
  promotions: BarChart3,
  audience: Users,
  voucher_series: Ticket,
  loyalty_programs: Star,
  points: Coins,
};

/* ── Page ───────────────────────────────────────────────────────────── */

export default function ConfigApisPage() {
  const { token, orgId } = useAuthStore();

  // Available API types
  const [apiTypes, setApiTypes] = useState<ApiType[]>([]);
  const [typesLoading, setTypesLoading] = useState(false);

  // Selected type + fetch state
  const [selectedType, setSelectedType] = useState<ApiType | null>(null);
  const [fetchLimit, setFetchLimit] = useState(50);
  const [fetching, setFetching] = useState(false);
  const [fetchResult, setFetchResult] = useState<FetchResult | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // History
  const [extractions, setExtractions] = useState<Extraction[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Tab
  const [activeTab, setActiveTab] = useState<ActiveTab>("fetch");

  const headers = useCallback(
    () => ({
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    }),
    [token]
  );

  /* ── Load available types ──────────────────────────────────────────── */

  const loadTypes = async () => {
    setTypesLoading(true);
    try {
      const resp = await fetch(`${API}/api/sources/config-apis/available`, {
        headers: headers(),
      });
      const data = await resp.json();
      setApiTypes(data.api_types || []);
    } catch {
      setApiTypes([]);
    }
    setTypesLoading(false);
  };

  useEffect(() => {
    if (token) loadTypes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  /* ── Fetch config data ─────────────────────────────────────────────── */

  const doFetch = async (apiType: string) => {
    setFetching(true);
    setFetchResult(null);
    setFetchError(null);
    try {
      const resp = await fetch(
        `${API}/api/sources/config-apis/fetch/${apiType}?org_id=${orgId}`,
        {
          method: "POST",
          headers: headers(),
          body: JSON.stringify({ limit: fetchLimit }),
        }
      );
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }
      const data = await resp.json();
      setFetchResult(data);
    } catch (e: unknown) {
      setFetchError(e instanceof Error ? e.message : "Fetch failed");
    }
    setFetching(false);
  };

  /* ── Load extractions history ──────────────────────────────────────── */

  const loadHistory = async () => {
    setHistoryLoading(true);
    try {
      const resp = await fetch(
        `${API}/api/sources/config-apis/extractions?org_id=${orgId}`,
        { headers: headers() }
      );
      const data = await resp.json();
      setExtractions(data.extractions || []);
    } catch {
      setExtractions([]);
    }
    setHistoryLoading(false);
  };

  /* ── Select a type ─────────────────────────────────────────────────── */

  const selectType = (apiType: ApiType) => {
    setSelectedType(apiType);
    setFetchResult(null);
    setFetchError(null);
  };

  /* ── Render helpers ────────────────────────────────────────────────── */

  const getIcon = (typeId: string) => {
    const Icon = API_ICONS[typeId] || Database;
    return <Icon className="h-4 w-4" />;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Configuration APIs Source
        </h1>
        <p className="text-sm text-gray-500">
          Fetch campaigns, promotions, audience groups, voucher series, loyalty
          programs, and points configurations from Capillary APIs.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-gray-100 p-1 w-fit">
        {(["fetch", "history"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => {
              setActiveTab(tab);
              if (tab === "history") loadHistory();
            }}
            className={cn(
              "rounded-md px-4 py-1.5 text-sm font-medium capitalize transition-colors",
              activeTab === tab
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            )}
          >
            {tab === "fetch" ? "Fetch Data" : "History"}
          </button>
        ))}
      </div>

      {/* ── Fetch Data Tab ──────────────────────────────────────────── */}
      {activeTab === "fetch" && (
        <div className="grid grid-cols-12 gap-4">
          {/* API Types list */}
          <div className="col-span-4 rounded-xl border border-gray-200 bg-white">
            <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
              <h3 className="text-sm font-semibold text-gray-700">
                API Types
              </h3>
              <button
                onClick={loadTypes}
                disabled={typesLoading}
                className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
              >
                <RefreshCw
                  className={cn(
                    "h-3.5 w-3.5",
                    typesLoading && "animate-spin"
                  )}
                />
              </button>
            </div>
            <div className="max-h-[500px] overflow-y-auto">
              {typesLoading && (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
                </div>
              )}
              {!typesLoading && apiTypes.length === 0 && (
                <p className="px-4 py-8 text-center text-xs text-gray-400">
                  No API types available
                </p>
              )}
              {apiTypes.map((at) => (
                <button
                  key={at.id}
                  onClick={() => selectType(at)}
                  className={cn(
                    "flex w-full items-center gap-3 border-b border-gray-50 px-4 py-3 text-left transition-colors hover:bg-violet-50",
                    selectedType?.id === at.id && "bg-violet-50 text-violet-700"
                  )}
                >
                  <span
                    className={cn(
                      "shrink-0 text-gray-400",
                      selectedType?.id === at.id && "text-violet-500"
                    )}
                  >
                    {getIcon(at.id)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium truncate">{at.label}</p>
                    <p className="text-[11px] text-gray-400 truncate">
                      {at.description}
                    </p>
                  </div>
                  <ChevronRight className="h-3.5 w-3.5 shrink-0 text-gray-300" />
                </button>
              ))}
            </div>
          </div>

          {/* Fetch panel */}
          <div className="col-span-8 space-y-4">
            {!selectedType && (
              <div className="rounded-xl border border-gray-200 bg-white px-6 py-16 text-center">
                <Database className="mx-auto h-8 w-8 text-gray-300" />
                <p className="mt-2 text-sm text-gray-400">
                  Select an API type to fetch configuration data
                </p>
              </div>
            )}

            {selectedType && (
              <>
                {/* Fetch controls */}
                <div className="rounded-xl border border-gray-200 bg-white p-5">
                  <div className="flex items-center gap-3 mb-4">
                    <span className="text-violet-500">{getIcon(selectedType.id)}</span>
                    <div>
                      <h3 className="text-sm font-semibold text-gray-900">
                        {selectedType.label}
                      </h3>
                      <p className="text-xs text-gray-500">
                        {selectedType.description}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-end gap-3">
                    <div className="w-36">
                      <label className="mb-1 block text-xs font-medium text-gray-600">
                        Max Records
                      </label>
                      <input
                        type="number"
                        value={fetchLimit}
                        onChange={(e) =>
                          setFetchLimit(
                            Math.max(1, Math.min(500, Number(e.target.value)))
                          )
                        }
                        min={1}
                        max={500}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-100"
                      />
                    </div>
                    <button
                      onClick={() => doFetch(selectedType.id)}
                      disabled={fetching}
                      className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-violet-700 disabled:opacity-50"
                    >
                      {fetching ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Download className="h-4 w-4" />
                      )}
                      Fetch
                    </button>
                  </div>
                </div>

                {/* Error */}
                {fetchError && (
                  <div className="rounded-xl border border-red-200 bg-red-50 p-4">
                    <div className="flex items-center gap-2">
                      <AlertCircle className="h-4 w-4 text-red-500" />
                      <p className="text-sm text-red-700">{fetchError}</p>
                    </div>
                  </div>
                )}

                {/* Results */}
                {fetchResult && (
                  <div className="rounded-xl border border-green-200 bg-green-50 p-5">
                    <div className="mb-3 flex items-center gap-2">
                      <Check className="h-5 w-5 text-green-600" />
                      <h3 className="text-sm font-semibold text-green-800">
                        Fetched {fetchResult.record_count}{" "}
                        {fetchResult.label.toLowerCase()} record(s)
                      </h3>
                    </div>
                    <div className="rounded-lg bg-white/60 p-4">
                      <pre className="whitespace-pre-wrap text-xs text-gray-700 max-h-80 overflow-y-auto">
                        {fetchResult.summary}
                      </pre>
                    </div>
                    <p className="mt-3 text-[10px] text-green-600">
                      Run ID: {fetchResult.run_id}
                    </p>
                  </div>
                )}

                {/* Raw data preview */}
                {fetchResult?.data && (
                  <details className="rounded-xl border border-gray-200 bg-white">
                    <summary className="cursor-pointer px-5 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50">
                      Raw JSON Response
                    </summary>
                    <div className="border-t border-gray-200 p-4">
                      <pre className="max-h-96 overflow-auto whitespace-pre-wrap text-xs text-gray-600 font-mono">
                        {JSON.stringify(fetchResult.data, null, 2).slice(
                          0,
                          10000
                        )}
                        {JSON.stringify(fetchResult.data, null, 2).length >
                          10000 && (
                          <span className="italic text-gray-400">
                            {"\n"}[Truncated — showing first 10,000 chars]
                          </span>
                        )}
                      </pre>
                    </div>
                  </details>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* ── History Tab ─────────────────────────────────────────────── */}
      {activeTab === "history" && (
        <div className="rounded-xl border border-gray-200 bg-white">
          <div className="flex items-center justify-between border-b border-gray-200 px-5 py-3">
            <h3 className="text-sm font-semibold text-gray-700">
              Past Extractions
            </h3>
            <button
              onClick={loadHistory}
              disabled={historyLoading}
              className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
            >
              <RefreshCw
                className={cn(
                  "h-3.5 w-3.5",
                  historyLoading && "animate-spin"
                )}
              />
            </button>
          </div>

          {historyLoading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
            </div>
          )}

          {!historyLoading && extractions.length === 0 && (
            <div className="px-5 py-12 text-center">
              <Database className="mx-auto h-8 w-8 text-gray-300" />
              <p className="mt-2 text-sm text-gray-400">
                No extractions yet. Fetch some config data to see history.
              </p>
            </div>
          )}

          {!historyLoading && extractions.length > 0 && (
            <div className="divide-y divide-gray-100">
              {/* Table header */}
              <div className="grid grid-cols-12 gap-4 bg-gray-50 px-5 py-2 text-xs font-medium text-gray-500 uppercase tracking-wide">
                <div className="col-span-4">API Type</div>
                <div className="col-span-2">Status</div>
                <div className="col-span-4">Date</div>
                <div className="col-span-2">Run ID</div>
              </div>

              {extractions.map((ext) => (
                <div
                  key={ext.id}
                  className="grid grid-cols-12 gap-4 px-5 py-3 items-center hover:bg-gray-50 transition-colors"
                >
                  <div className="col-span-4 flex items-center gap-2">
                    <span className="text-gray-400">
                      {getIcon(ext.api_type)}
                    </span>
                    <span className="text-sm font-medium text-gray-900">
                      {ext.label}
                    </span>
                  </div>
                  <div className="col-span-2">
                    <span
                      className={cn(
                        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium",
                        ext.status === "complete"
                          ? "bg-green-100 text-green-700"
                          : ext.status === "error"
                          ? "bg-red-100 text-red-700"
                          : "bg-yellow-100 text-yellow-700"
                      )}
                    >
                      {ext.status === "complete" && (
                        <Check className="h-2.5 w-2.5" />
                      )}
                      {ext.status === "error" && (
                        <AlertCircle className="h-2.5 w-2.5" />
                      )}
                      {ext.status}
                    </span>
                  </div>
                  <div className="col-span-4 text-xs text-gray-500">
                    {formatDate(ext.created_at)}
                  </div>
                  <div className="col-span-2 text-[10px] text-gray-400 font-mono truncate">
                    {ext.id.slice(0, 8)}...
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
