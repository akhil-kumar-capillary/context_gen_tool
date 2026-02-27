"use client";

import { useEffect, useState } from "react";
import { Loader2, FileCode } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth-store";
import { useDatabricksStore } from "@/stores/databricks-store";
import { AnalysisDashboard } from "./analysis/analysis-dashboard";

interface SqlRecord {
  id: number;
  notebook_path: string;
  cleaned_sql: string;
  org_id: string;
  is_valid: boolean;
  sql_hash: string;
}

export function RunDetailView() {
  const { token } = useAuthStore();
  const { activeExtractionId, activeAnalysisId } = useDatabricksStore();

  const [sqls, setSqls] = useState<SqlRecord[]>([]);
  const [loading, setLoading] = useState(false);

  // Load SQLs only when we have an extraction but no analysis
  useEffect(() => {
    if (!activeExtractionId || activeAnalysisId) return;
    const load = async () => {
      setLoading(true);
      try {
        const data = await apiClient.get<{ sqls: SqlRecord[] }>(
          `/api/sources/databricks/extract/runs/${activeExtractionId}/sqls?valid_only=true`,
          { token: token || undefined }
        );
        setSqls(data.sqls.slice(0, 100));
      } catch {
        // Silently handle — user can retry or run analysis
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [activeExtractionId, activeAnalysisId, token]);

  if (!activeExtractionId && !activeAnalysisId) return null;

  // If we have an analysis, show the full dashboard
  if (activeAnalysisId) {
    return <AnalysisDashboard analysisId={activeAnalysisId} />;
  }

  // Extraction-only: show basic SQL list
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6">
      <div className="mb-4 flex items-center gap-2 border-b border-gray-100 pb-2">
        <FileCode className="h-4 w-4 text-violet-600" />
        <span className="text-sm font-medium text-violet-600">
          Extracted SQLs
        </span>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
        </div>
      ) : (
        <div className="max-h-96 overflow-y-auto">
          {sqls.length === 0 ? (
            <p className="py-4 text-center text-sm text-gray-500">
              No SQL records
            </p>
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
                      {sql.notebook_path?.split("/").pop() ||
                        sql.notebook_path}
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
    </div>
  );
}
