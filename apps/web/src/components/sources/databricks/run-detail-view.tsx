"use client";

import { useEffect, useState } from "react";
import { Loader2, FileCode, Database, BarChart3 } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import { useDatabricksStore } from "@/stores/databricks-store";

type TabId = "sqls" | "notebooks" | "fingerprints";

interface SqlRecord {
  id: number;
  notebook_path: string;
  cleaned_sql: string;
  org_id: string;
  is_valid: boolean;
  sql_hash: string;
}

interface NotebookRecord {
  id: number;
  notebook_path: string;
  notebook_name: string;
  language: string;
  status: string;
  is_attached_to_jobs: string;
  job_name: string;
}

interface Fingerprint {
  id: string;
  tables: string[];
  frequency: number;
  functions: string[];
  raw_sql: string;
}

export function RunDetailView() {
  const { token } = useAuthStore();
  const { activeExtractionId, activeAnalysisId } = useDatabricksStore();

  const [tab, setTab] = useState<TabId>("sqls");
  const [sqls, setSqls] = useState<SqlRecord[]>([]);
  const [notebooks, setNotebooks] = useState<NotebookRecord[]>([]);
  const [fingerprints, setFingerprints] = useState<Fingerprint[]>([]);
  const [loading, setLoading] = useState(false);
  const [totalFp, setTotalFp] = useState(0);

  useEffect(() => {
    if (!activeExtractionId && !activeAnalysisId) return;
    const load = async () => {
      setLoading(true);
      try {
        if (tab === "sqls" && activeExtractionId) {
          const data = await apiClient.get<{ sqls: SqlRecord[] }>(
            `/api/sources/databricks/extract/runs/${activeExtractionId}/sqls?valid_only=true`,
            { token: token || undefined }
          );
          setSqls(data.sqls.slice(0, 100));
        } else if (tab === "notebooks" && activeExtractionId) {
          const data = await apiClient.get<{ notebooks: NotebookRecord[] }>(
            `/api/sources/databricks/extract/runs/${activeExtractionId}/notebooks`,
            { token: token || undefined }
          );
          setNotebooks(data.notebooks);
        } else if (tab === "fingerprints" && activeAnalysisId) {
          const data = await apiClient.get<{
            fingerprints: Fingerprint[];
            total: number;
          }>(
            `/api/sources/databricks/analysis/${activeAnalysisId}/fingerprints?limit=50`,
            { token: token || undefined }
          );
          setFingerprints(data.fingerprints);
          setTotalFp(data.total);
        }
      } catch (err) {
        console.error("Failed to load detail:", err);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [tab, activeExtractionId, activeAnalysisId, token]);

  if (!activeExtractionId && !activeAnalysisId) return null;

  const tabs: { id: TabId; label: string; icon: React.ReactNode; enabled: boolean }[] = [
    { id: "sqls", label: "SQLs", icon: <FileCode className="h-4 w-4" />, enabled: !!activeExtractionId },
    { id: "notebooks", label: "Notebooks", icon: <Database className="h-4 w-4" />, enabled: !!activeExtractionId },
    { id: "fingerprints", label: "Fingerprints", icon: <BarChart3 className="h-4 w-4" />, enabled: !!activeAnalysisId },
  ];

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6">
      <div className="mb-4 flex gap-1 border-b border-gray-100">
        {tabs
          .filter((t) => t.enabled)
          .map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "flex items-center gap-1.5 border-b-2 px-3 pb-2 text-sm font-medium transition-colors",
                tab === t.id
                  ? "border-violet-600 text-violet-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              )}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
        </div>
      ) : (
        <>
          {tab === "sqls" && (
            <div className="max-h-96 overflow-y-auto">
              {sqls.length === 0 ? (
                <p className="py-4 text-center text-sm text-gray-500">No SQL records</p>
              ) : (
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-gray-200 bg-gray-50 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                      <th className="px-3 py-2">Notebook</th>
                      <th className="px-3 py-2">Org</th>
                      <th className="px-3 py-2">SQL Preview</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sqls.map((sql) => (
                      <tr key={sql.id} className="border-b border-gray-50">
                        <td className="px-3 py-2 font-mono text-gray-600">
                          {sql.notebook_path?.split("/").pop() || sql.notebook_path}
                        </td>
                        <td className="px-3 py-2">{sql.org_id}</td>
                        <td className="max-w-sm truncate px-3 py-2 font-mono text-gray-500">
                          {sql.cleaned_sql?.slice(0, 120)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {tab === "notebooks" && (
            <div className="max-h-96 overflow-y-auto">
              {notebooks.length === 0 ? (
                <p className="py-4 text-center text-sm text-gray-500">No notebooks</p>
              ) : (
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-gray-200 bg-gray-50 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                      <th className="px-3 py-2">Name</th>
                      <th className="px-3 py-2">Language</th>
                      <th className="px-3 py-2">Job</th>
                      <th className="px-3 py-2">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {notebooks.map((nb) => (
                      <tr key={nb.id} className="border-b border-gray-50">
                        <td className="px-3 py-2 font-mono text-gray-600">
                          {nb.notebook_name || nb.notebook_path?.split("/").pop()}
                        </td>
                        <td className="px-3 py-2">{nb.language}</td>
                        <td className="px-3 py-2 text-gray-500">
                          {nb.is_attached_to_jobs === "Yes" ? nb.job_name || "Yes" : "-"}
                        </td>
                        <td className="px-3 py-2">{nb.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {tab === "fingerprints" && (
            <div className="max-h-96 overflow-y-auto">
              {fingerprints.length === 0 ? (
                <p className="py-4 text-center text-sm text-gray-500">No fingerprints</p>
              ) : (
                <>
                  <p className="mb-2 text-xs text-gray-500">
                    Showing {fingerprints.length} of {totalFp} fingerprints
                  </p>
                  <div className="space-y-2">
                    {fingerprints.map((fp) => (
                      <div
                        key={fp.id}
                        className="rounded-lg border border-gray-200 p-3"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-medium text-gray-700">
                            {fp.tables.join(", ")}
                          </span>
                          <span className="text-xs text-gray-400">
                            freq: {fp.frequency}
                          </span>
                        </div>
                        {fp.functions.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-1">
                            {fp.functions.slice(0, 8).map((fn) => (
                              <span
                                key={fn}
                                className="rounded bg-violet-50 px-1.5 py-0.5 text-[10px] text-violet-600"
                              >
                                {fn}
                              </span>
                            ))}
                          </div>
                        )}
                        <div className="mt-1 truncate font-mono text-[10px] text-gray-400">
                          {fp.raw_sql?.slice(0, 150)}
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
