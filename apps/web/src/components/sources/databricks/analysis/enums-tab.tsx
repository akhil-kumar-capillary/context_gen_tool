"use client";

import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronRight, Search, Tag } from "lucide-react";
import { useAnalysisDashboardStore } from "@/stores/analysis-dashboard-store";

export function EnumsTab() {
  const counters = useAnalysisDashboardStore((s) => s.counters);
  const [expandedCols, setExpandedCols] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");

  const literalVals = counters?.literal_vals;
  const aliasConv = counters?.alias_conv;

  const { filteredLiterals, totalFiltered } = useMemo(() => {
    if (!literalVals) return { filteredLiterals: [], totalFiltered: 0 };
    const all = Object.entries(literalVals)
      .filter(([col, vals]) => {
        if (!search) return true;
        const lower = search.toLowerCase();
        return (
          col.toLowerCase().includes(lower) ||
          vals.some(([v]) => String(v).toLowerCase().includes(lower))
        );
      })
      .sort((a, b) => b[1].length - a[1].length);
    return { filteredLiterals: all.slice(0, 50), totalFiltered: all.length };
  }, [literalVals, search]);

  const toggleCol = (col: string) => {
    setExpandedCols((prev) => {
      const next = new Set(prev);
      if (next.has(col)) next.delete(col);
      else next.add(col);
      return next;
    });
  };

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-gray-500">
        Enum-Like Values & Aliases
      </h3>
      <p className="text-xs text-gray-400">
        Columns with discrete literal values found across queries, plus table
        alias conventions
      </p>

      {!literalVals || Object.keys(literalVals).length === 0 ? (
        <div className="h-[300px] flex items-center justify-center text-sm text-gray-400">
          No enum/literal values found
        </div>
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="space-y-4"
        >
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search columns or values..."
              className="w-full pl-9 pr-3 py-2 rounded-lg border border-gray-200 bg-white text-sm placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-violet-300"
            />
          </div>

          <div className="text-xs text-gray-400">
            {totalFiltered > 50
              ? `Showing 50 of ${totalFiltered} columns with enum-like values`
              : `${filteredLiterals.length} columns with enum-like values`}
          </div>

          {/* Literal values accordion */}
          <div className="rounded-xl border border-gray-200 bg-white overflow-hidden divide-y divide-gray-100">
            {filteredLiterals.map(([col, vals]) => (
              <div key={col}>
                <button
                  onClick={() => toggleCol(col)}
                  className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-50 transition-colors"
                >
                  {expandedCols.has(col) ? (
                    <ChevronDown className="h-4 w-4 text-gray-400 flex-shrink-0" />
                  ) : (
                    <ChevronRight className="h-4 w-4 text-gray-400 flex-shrink-0" />
                  )}
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <Tag className="h-3.5 w-3.5 text-violet-400 flex-shrink-0" />
                    <span className="text-sm font-mono font-medium truncate text-gray-700">
                      {col}
                    </span>
                  </div>
                  <span className="text-xs text-gray-400 tabular-nums flex-shrink-0">
                    {vals.length} values
                  </span>
                </button>

                <AnimatePresence>
                  {expandedCols.has(col) && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div className="px-4 pb-3 pl-11">
                        <div className="flex flex-wrap gap-1.5">
                          {vals.slice(0, 100).map(([value, count], i) => (
                            <motion.span
                              key={i}
                              initial={{ scale: 0.8, opacity: 0 }}
                              animate={{ scale: 1, opacity: 1 }}
                              transition={{
                                delay: Math.min(i * 0.02, 1),
                                duration: 0.15,
                              }}
                              className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-mono bg-violet-50 text-violet-600 border border-violet-200 hover:bg-violet-100 transition-colors"
                            >
                              {String(value)}
                              <span className="text-[9px] text-violet-400 ml-0.5">
                                ×{count}
                              </span>
                            </motion.span>
                          ))}
                          {vals.length > 100 && (
                            <span className="inline-flex items-center px-2 py-1 rounded-md text-[10px] text-gray-400">
                              +{vals.length - 100} more values
                            </span>
                          )}
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            ))}
          </div>

          {/* Alias conventions */}
          {aliasConv && Object.keys(aliasConv).length > 0 && (
            <div className="space-y-2">
              <h3 className="text-sm font-medium text-gray-500">
                Alias Conventions
              </h3>
              <div className="rounded-xl border border-gray-200 bg-white overflow-hidden divide-y divide-gray-100">
                {Object.entries(aliasConv)
                  .slice(0, 20)
                  .map(([table, aliases]) => (
                    <div
                      key={table}
                      className="px-4 py-3"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono font-medium text-gray-700">
                          {table}
                        </span>
                        <div className="flex gap-1">
                          {aliases.map(([alias, count], i) => (
                            <span
                              key={i}
                              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono bg-blue-50 text-blue-600 border border-blue-200"
                            >
                              {String(alias)}
                              <span className="text-[9px] text-blue-400">
                                ×{count}
                              </span>
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </motion.div>
      )}
    </div>
  );
}
