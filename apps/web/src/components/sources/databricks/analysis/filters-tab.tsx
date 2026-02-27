"use client";

import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useAnalysisDashboardStore } from "@/stores/analysis-dashboard-store";

const TIER_COLORS: Record<string, string> = {
  MANDATORY: "rgb(239, 68, 68)",
  "TABLE-DEFAULT": "rgb(249, 115, 22)",
  COMMON: "rgb(234, 179, 8)",
  SITUATIONAL: "rgb(96, 165, 250)",
};

const TIER_BG: Record<string, string> = {
  MANDATORY: "bg-red-50 border-red-200 text-red-600",
  "TABLE-DEFAULT": "bg-orange-50 border-orange-200 text-orange-600",
  COMMON: "bg-yellow-50 border-yellow-200 text-yellow-700",
  SITUATIONAL: "bg-blue-50 border-blue-200 text-blue-600",
};

function FilterRow({
  filter,
}: {
  filter: {
    condition: string;
    tier: string;
    count: number;
    global_pct: number;
    table_pcts: Record<string, number>;
  };
}) {
  const [expanded, setExpanded] = useState(false);
  const tables = Object.entries(filter.table_pcts || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 20);

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left px-4 py-2.5 hover:bg-gray-50 transition-colors flex items-center gap-2"
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3 text-gray-400 flex-shrink-0" />
        ) : (
          <ChevronRight className="h-3 w-3 text-gray-400 flex-shrink-0" />
        )}
        <span className="text-xs font-mono truncate flex-1">
          {filter.condition}
        </span>
        <span className="text-[10px] text-gray-400 tabular-nums flex-shrink-0">
          {filter.count.toLocaleString()} ·{" "}
          {Math.round(filter.global_pct * 100)}% ·{" "}
          {Object.keys(filter.table_pcts || {}).length} tables
        </span>
      </button>
      <AnimatePresence>
        {expanded && tables.length > 0 && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-3 pl-9">
              <div className="flex flex-wrap gap-1.5">
                {tables.map(([table, pct]) => (
                  <span
                    key={table}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono bg-gray-50 text-gray-500 border border-gray-200"
                  >
                    {table}
                    <span className="text-[9px] opacity-60">
                      {Math.round(pct * 100)}%
                    </span>
                  </span>
                ))}
                {Object.keys(filter.table_pcts || {}).length > 20 && (
                  <span className="inline-flex items-center px-2 py-0.5 text-[10px] text-gray-400">
                    +{Object.keys(filter.table_pcts).length - 20} more
                  </span>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function FiltersTab() {
  const filters = useAnalysisDashboardStore((s) => s.filters);
  const [expandedTier, setExpandedTier] = useState<string | null>(null);

  const { tierGroups, tierCounts } = useMemo(() => {
    if (!filters?.length)
      return {
        tierGroups: {} as Record<string, typeof filters>,
        tierCounts: {} as Record<string, number>,
      };
    const groups: Record<string, typeof filters> = {};
    const counts: Record<string, number> = {};
    for (const f of filters) {
      if (!groups[f.tier]) groups[f.tier] = [];
      groups[f.tier].push(f);
      counts[f.tier] = (counts[f.tier] || 0) + 1;
    }
    return { tierGroups: groups, tierCounts: counts };
  }, [filters]);

  const topTableBars = useMemo(() => {
    if (!filters?.length) return [];
    const tableCountMap = new Map<string, number>();
    for (const f of filters) {
      for (const [table] of Object.entries(f.table_pcts || {})) {
        tableCountMap.set(
          table,
          (tableCountMap.get(table) || 0) + f.count
        );
      }
    }
    return Array.from(tableCountMap.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 15);
  }, [filters]);

  const maxTableCount = topTableBars.length > 0 ? topTableBars[0][1] : 1;

  if (!filters?.length) {
    return (
      <div className="space-y-2">
        <h3 className="text-sm font-medium text-gray-500">
          Filter Classification
        </h3>
        <div className="h-[400px] flex items-center justify-center text-sm text-gray-400">
          No filter classification data
        </div>
      </div>
    );
  }

  const tiers = ["MANDATORY", "TABLE-DEFAULT", "COMMON", "SITUATIONAL"];

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-gray-500">
        Filter Classification
      </h3>
      <p className="text-xs text-gray-400">
        WHERE conditions classified by frequency into tiers: Mandatory (&gt;50%),
        Table-Default (&gt;30%), Common (&gt;10%), Situational
      </p>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="space-y-4"
      >
        {/* Tier summary cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {tiers.map((tier) => {
            const count = tierCounts[tier] || 0;
            if (count === 0) return null;
            return (
              <button
                key={tier}
                onClick={() =>
                  setExpandedTier(expandedTier === tier ? null : tier)
                }
                className={`rounded-lg border border-gray-200 p-3 text-left transition-all hover:scale-[1.02] bg-white ${
                  expandedTier === tier ? "ring-2 ring-violet-300" : ""
                }`}
              >
                <div className="flex items-center gap-2">
                  <div
                    className="w-3 h-3 rounded-sm flex-shrink-0"
                    style={{ background: TIER_COLORS[tier] }}
                  />
                  <span className="text-xs font-semibold text-gray-700">
                    {tier}
                  </span>
                </div>
                <p className="text-xl font-bold tabular-nums mt-1 text-gray-900">
                  {count}
                </p>
                <p className="text-[10px] text-gray-400">conditions</p>
              </button>
            );
          })}
        </div>

        {/* Expanded tier */}
        <AnimatePresence mode="wait">
          {expandedTier && tierGroups[expandedTier] && (
            <motion.div
              key={expandedTier}
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden"
            >
              <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
                <div className="px-4 py-2.5 border-b border-gray-100 bg-gray-50 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div
                      className="w-3 h-3 rounded-sm"
                      style={{ background: TIER_COLORS[expandedTier] }}
                    />
                    <span className="text-sm font-semibold text-gray-700">
                      {expandedTier}
                    </span>
                    <span className="text-xs text-gray-400">
                      ({tierCounts[expandedTier]} conditions)
                    </span>
                  </div>
                  <button
                    onClick={() => setExpandedTier(null)}
                    className="text-xs text-gray-400 hover:text-gray-700"
                  >
                    Close
                  </button>
                </div>
                <div className="divide-y divide-gray-100 max-h-[400px] overflow-y-auto">
                  {tierGroups[expandedTier].slice(0, 50).map((f, i) => (
                    <FilterRow key={i} filter={f} />
                  ))}
                  {tierGroups[expandedTier].length > 50 && (
                    <div className="px-4 py-2 text-xs text-gray-400 text-center">
                      +{tierGroups[expandedTier].length - 50} more conditions
                    </div>
                  )}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Top tables bar chart */}
        {topTableBars.length > 0 && (
          <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-3">
            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              Top Tables by Filter Frequency
            </h4>
            <div className="space-y-1.5">
              {topTableBars.map(([table, count]) => (
                <div key={table} className="flex items-center gap-3">
                  <span className="text-[11px] font-mono text-gray-500 w-[140px] truncate text-right flex-shrink-0">
                    {table}
                  </span>
                  <div className="flex-1 h-5 rounded bg-gray-100 overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{
                        width: `${(count / maxTableCount) * 100}%`,
                      }}
                      transition={{ duration: 0.5, ease: "easeOut" }}
                      className="h-full rounded bg-violet-300"
                    />
                  </div>
                  <span className="text-[10px] font-mono text-gray-400 tabular-nums w-[50px] text-right">
                    {count.toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Full filter table */}
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50">
                <th className="px-3 py-2 text-left text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
                  Condition
                </th>
                <th className="px-3 py-2 text-left text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
                  Tier
                </th>
                <th className="px-3 py-2 text-right text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
                  Count
                </th>
                <th className="px-3 py-2 text-right text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
                  Global %
                </th>
                <th className="px-3 py-2 text-right text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
                  Tables
                </th>
              </tr>
            </thead>
            <tbody>
              {filters.slice(0, 50).map((f, i) => (
                <tr
                  key={i}
                  className="border-b border-gray-50 last:border-0 hover:bg-gray-50 transition-colors"
                >
                  <td className="px-3 py-2 text-xs font-mono truncate max-w-[300px] text-gray-700">
                    {f.condition}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-flex px-1.5 py-0.5 rounded text-[10px] font-semibold border ${
                        TIER_BG[f.tier] || ""
                      }`}
                    >
                      {f.tier}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-xs text-right font-mono tabular-nums text-gray-600">
                    {f.count.toLocaleString()}
                  </td>
                  <td className="px-3 py-2 text-xs text-right font-mono tabular-nums text-gray-600">
                    {Math.round(f.global_pct * 100)}%
                  </td>
                  <td className="px-3 py-2 text-xs text-right font-mono tabular-nums text-gray-600">
                    {Object.keys(f.table_pcts || {}).length}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filters.length > 50 && (
            <div className="px-3 py-2 text-xs text-gray-400 text-center border-t border-gray-100">
              Showing 50 of {filters.length} conditions
            </div>
          )}
        </div>
      </motion.div>
    </div>
  );
}
