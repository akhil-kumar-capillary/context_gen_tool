import { create } from "zustand";
import { apiClient } from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Data types (ported from reference analysis-store.ts)
// ---------------------------------------------------------------------------

export interface NotebookMeta {
  id: number;
  notebook_path: string;
  notebook_name: string | null;
  user_name: string | null;
  object_id: string | null;
  language: string | null;
  has_content: boolean;
  file_type: string | null;
  status: string;
  is_attached_to_jobs: string;
  job_id: string | null;
  job_name: string | null;
  cont_success_run_count: number | null;
  earliest_run_date: string | null;
  trigger_type: string | null;
  sql_count: number;
  nb_created_at: string | null;
  nb_modified_at: string | null;
}

export interface ExtractedSQL {
  id: number;
  notebook_path: string;
  notebook_name: string | null;
  user_name: string | null;
  cell_number: number;
  cleaned_sql: string | null;
  sql_hash: string | null;
  is_valid: boolean;
  file_type: string | null;
  org_id: string | null;
  language: string | null;
}

export interface Fingerprint {
  id: string;
  raw_sql: string;
  canonical_sql: string;
  nl_question: string | null;
  frequency: number;
  tables: string[];
  qualified_columns: [string, string][];
  functions: string[];
  join_graph: {
    left: string;
    right: string;
    join_type: string;
    on_condition: string;
  }[];
  where_conditions: string[];
  group_by: string[];
  having_conditions: string[];
  order_by: string[];
  literals: Record<string, string[]>;
  case_when_blocks: string[];
  window_exprs: string[];
  has_cte: boolean;
  has_window: boolean;
  has_union: boolean;
  has_case: boolean;
  has_subquery: boolean;
  has_having: boolean;
  has_order_by: boolean;
  has_distinct: boolean;
  has_limit: boolean;
  limit_value: number | null;
  select_col_count: number;
  alias_map: Record<string, string>;
}

export interface Cluster {
  sig: string;
  count: number;
  n_unique: number;
  rep_sql: string;
  cpx_sql: string;
  functions: string[];
  group_by: string[];
  where: string[];
  tables: string[];
}

export interface ClassifiedFilter {
  condition: string;
  tier: "MANDATORY" | "TABLE-DEFAULT" | "COMMON" | "SITUATIONAL";
  global_pct: number;
  table_pcts: Record<string, number>;
  count: number;
}

export type CounterEntry = [string | string[] | number, number];

export interface Counters {
  table: CounterEntry[];
  column: CounterEntry[];
  function: CounterEntry[];
  join_pair: CounterEntry[];
  join_cond: CounterEntry[];
  where: CounterEntry[];
  group_by: CounterEntry[];
  agg_pattern: CounterEntry[];
  order_by: CounterEntry[];
  structural: CounterEntry[];
  limit_val: CounterEntry[];
  select_cols: CounterEntry[];
  literal_vals: Record<string, [string, number][]>;
  alias_conv: Record<string, [string, number][]>;
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

interface AnalysisDashboardState {
  // Data
  counters: Counters | null;
  totalWeight: number;
  clusters: Cluster[];
  filters: ClassifiedFilter[];
  fingerprints: Fingerprint[];
  totalFingerprints: number;
  notebooks: NotebookMeta[];
  extractedSqls: ExtractedSQL[];

  // UI state
  activeTab: string;
  selectedTable: string | null;
  selectedQueryId: string | null;
  isLoaded: boolean;
  isLoading: boolean;
  error: string | null;

  // Actions
  setActiveTab: (tab: string) => void;
  setSelectedTable: (table: string | null) => void;
  setSelectedQueryId: (id: string | null) => void;
  loadAnalysisData: (analysisId: string, token: string) => Promise<void>;
  reset: () => void;
}

const initialState = {
  counters: null,
  totalWeight: 0,
  clusters: [],
  filters: [],
  fingerprints: [],
  totalFingerprints: 0,
  notebooks: [],
  extractedSqls: [],
  activeTab: "overview",
  selectedTable: null,
  selectedQueryId: null,
  isLoaded: false,
  isLoading: false,
  error: null,
};

export const useAnalysisDashboardStore = create<AnalysisDashboardState>(
  (set, get) => ({
    ...initialState,

    setActiveTab: (tab) => set({ activeTab: tab }),
    setSelectedTable: (table) => set({ selectedTable: table }),
    setSelectedQueryId: (id) => set({ selectedQueryId: id }),

    loadAnalysisData: async (analysisId: string, token: string) => {
      if (get().isLoading) return;
      set({ isLoading: true, error: null });

      try {
        // Fetch analysis, fingerprints, and notebooks in parallel
        const [analysisData, fpData, nbData] = await Promise.all([
          apiClient.get<{
            counters: Counters;
            clusters: Cluster[];
            classified_filters: ClassifiedFilter[] | Record<string, ClassifiedFilter[]>;
            fingerprints_summary: Fingerprint[];
            literal_vals: Record<string, [string, number][]>;
            alias_conv: Record<string, [string, number][]>;
            total_weight: number;
            run_id: string;
          }>(`/api/sources/databricks/analysis/${analysisId}`, { token }),
          apiClient.get<{ fingerprints: Fingerprint[]; total: number }>(
            `/api/sources/databricks/analysis/${analysisId}/fingerprints?limit=500`,
            { token }
          ),
          apiClient.get<{ notebooks: NotebookMeta[]; count: number }>(
            `/api/sources/databricks/analysis/${analysisId}/notebooks`,
            { token }
          ),
        ]);

        // Fetch extracted SQLs for the source extraction run (for notebook detail)
        let extractedSqls: ExtractedSQL[] = [];
        if (analysisData.run_id) {
          try {
            const sqlData = await apiClient.get<{
              sqls: ExtractedSQL[];
              count: number;
            }>(
              `/api/sources/databricks/extract/runs/${analysisData.run_id}/sqls`,
              { token }
            );
            extractedSqls = sqlData.sqls || [];
          } catch {
            // Non-critical — notebooks tab will just show counts without cell details
          }
        }

        // Normalize classified_filters — backend may store as object or array
        let filters: ClassifiedFilter[] = [];
        if (Array.isArray(analysisData.classified_filters)) {
          filters = analysisData.classified_filters;
        } else if (
          analysisData.classified_filters &&
          typeof analysisData.classified_filters === "object"
        ) {
          // Flatten if stored as { tier: ClassifiedFilter[] }
          filters = Object.values(analysisData.classified_filters).flat();
        }

        // Merge literal_vals and alias_conv into counters
        const counters = analysisData.counters || ({} as Counters);
        if (analysisData.literal_vals) {
          counters.literal_vals = analysisData.literal_vals;
        }
        if (analysisData.alias_conv) {
          counters.alias_conv = analysisData.alias_conv;
        }

        set({
          counters,
          totalWeight: analysisData.total_weight || 0,
          clusters: analysisData.clusters || [],
          filters,
          fingerprints: fpData.fingerprints || [],
          totalFingerprints: fpData.total || 0,
          notebooks: nbData.notebooks || [],
          extractedSqls,
          isLoaded: true,
          isLoading: false,
        });
      } catch (err) {
        set({
          isLoading: false,
          error: err instanceof Error ? err.message : "Failed to load analysis",
        });
      }
    },

    reset: () => set(initialState),
  })
);
