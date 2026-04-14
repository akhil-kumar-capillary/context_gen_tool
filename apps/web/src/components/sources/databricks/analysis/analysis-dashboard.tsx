"use client";

import React, { useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Loader2,
  X,
  Activity,
  LayoutGrid,
  GitBranch,
  Filter,
  Layers,
  Tag,
  Code2,
  BookOpen,
} from "lucide-react";
import { useAnalysisDashboardStore } from "@/stores/analysis-dashboard-store";
import { useAuthStore } from "@/stores/auth-store";
import { OverviewTab } from "./overview-tab";
import { NotebooksTab } from "./notebooks-tab";
import { SchemaTab } from "./schema-tab";
import { FiltersTab } from "./filters-tab";
import { PatternsTab } from "./patterns-tab";
import { EnumsTab } from "./enums-tab";
import { QueriesTab } from "./queries-tab";

// ---------------------------------------------------------------------------
// Tab config
// ---------------------------------------------------------------------------
const TABS = [
  { id: "overview", label: "Overview", icon: LayoutGrid },
  { id: "notebooks", label: "Notebooks", icon: BookOpen },
  { id: "schema", label: "Schema & Joins", icon: GitBranch },
  { id: "filters", label: "Filters", icon: Filter },
  { id: "patterns", label: "Patterns", icon: Layers },
  { id: "enums", label: "Enums", icon: Tag },
  { id: "queries", label: "All Queries", icon: Code2 },
] as const;

const TAB_CONTENT: Record<string, React.ComponentType> = {
  overview: OverviewTab,
  notebooks: NotebooksTab,
  schema: SchemaTab,
  filters: FiltersTab,
  patterns: PatternsTab,
  enums: EnumsTab,
  queries: QueriesTab,
};

// ---------------------------------------------------------------------------
// Stat Card (memoized – pure presentational)
// ---------------------------------------------------------------------------
const StatCard = React.memo(function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-border bg-background p-4"
    >
      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 text-2xl font-bold tabular-nums text-foreground">
        {typeof value === "number" ? value.toLocaleString() : value}
      </p>
      {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
    </motion.div>
  );
});

// ---------------------------------------------------------------------------
// Main Dashboard
// ---------------------------------------------------------------------------
export function AnalysisDashboard({ analysisId }: { analysisId: string }) {
  const { token, orgId } = useAuthStore();
  const activeTab = useAnalysisDashboardStore((s) => s.activeTab);
  const setActiveTab = useAnalysisDashboardStore((s) => s.setActiveTab);
  const isLoaded = useAnalysisDashboardStore((s) => s.isLoaded);
  const isLoading = useAnalysisDashboardStore((s) => s.isLoading);
  const error = useAnalysisDashboardStore((s) => s.error);
  const counters = useAnalysisDashboardStore((s) => s.counters);
  const totalWeight = useAnalysisDashboardStore((s) => s.totalWeight);
  const totalFingerprints = useAnalysisDashboardStore((s) => s.totalFingerprints);
  const clusters = useAnalysisDashboardStore((s) => s.clusters);
  const selectedTable = useAnalysisDashboardStore((s) => s.selectedTable);
  const setSelectedTable = useAnalysisDashboardStore((s) => s.setSelectedTable);
  const loadAnalysisData = useAnalysisDashboardStore((s) => s.loadAnalysisData);
  const reset = useAnalysisDashboardStore((s) => s.reset);

  const clearTableFilter = useCallback(() => setSelectedTable(null), [setSelectedTable]);

  // Load data on mount or when analysisId changes
  useEffect(() => {
    if (!token || !analysisId) return;
    reset();
    loadAnalysisData(analysisId, token, orgId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysisId, token]);

  // Loading state
  if (isLoading && !isLoaded) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
        <span className="ml-3 text-sm text-muted-foreground">
          Loading analysis data...
        </span>
      </div>
    );
  }

  // Error state
  if (error && !isLoaded) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-sm text-red-500">{error}</p>
      </div>
    );
  }

  // Not loaded
  if (!isLoaded) {
    return (
      <div className="flex items-center justify-center py-20 text-sm text-muted-foreground">
        Run analysis on an extraction to see visualizations
      </div>
    );
  }

  const TabContent = TAB_CONTENT[activeTab] || OverviewTab;

  return (
    <div className="space-y-6 p-6">
      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          label="Total Queries"
          value={totalWeight}
          sub="frequency-weighted"
        />
        <StatCard label="Unique Patterns" value={totalFingerprints} />
        <StatCard label="Tables" value={counters?.table?.length || 0} />
        <StatCard label="Clusters" value={clusters.length} />
      </div>

      {/* Selected table filter indicator */}
      <AnimatePresence>
        {selectedTable && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="flex items-center gap-2 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2"
          >
            <Activity className="h-4 w-4 text-primary" />
            <span className="text-sm text-foreground">
              Filtering by table:{" "}
              <span className="font-mono font-bold text-primary">
                {selectedTable}
              </span>
            </span>
            <button
              onClick={clearTableFilter}
              className="ml-auto rounded p-1 text-primary transition-colors hover:bg-primary/10"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Tab navigation */}
      <div className="flex items-center gap-1 overflow-x-auto rounded-xl border border-border bg-muted/50 p-1">
        {TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`
                relative flex items-center gap-2 whitespace-nowrap rounded-lg px-4 py-2.5 text-sm font-medium
                transition-all duration-200
                ${
                  isActive
                    ? "text-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }
              `}
            >
              {isActive && (
                <motion.div
                  layoutId="activeAnalysisTab"
                  className="absolute inset-0 rounded-lg border border-border bg-background shadow-sm"
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                />
              )}
              <span className="relative z-10 flex items-center gap-2">
                <tab.icon className="h-4 w-4" />
                {tab.label}
              </span>
            </button>
          );
        })}
      </div>

      {/* Tab content with animation */}
      <AnimatePresence mode="wait">
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.2 }}
        >
          <TabContent />
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
