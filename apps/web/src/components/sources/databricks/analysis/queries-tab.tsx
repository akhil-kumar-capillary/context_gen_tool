"use client";

import { useState, useMemo, Fragment } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  ChevronsLeft,
  ChevronsRight,
  ArrowUpDown,
  Search,
  Table2,
  Columns3,
  GitBranch,
  Filter,
  BarChart3,
  Braces,
  Layers,
  Hash,
} from "lucide-react";
import {
  useAnalysisDashboardStore,
  type Fingerprint,
} from "@/stores/analysis-dashboard-store";
import { Badge } from "./shared";


// ---------------------------------------------------------------------------
// Structural Flags
// ---------------------------------------------------------------------------
function StructuralFlags({ fp }: { fp: Fingerprint }) {
  const flags = [
    { key: "CTE", on: fp.has_cte },
    { key: "WINDOW", on: fp.has_window },
    { key: "UNION", on: fp.has_union },
    { key: "CASE", on: fp.has_case },
    { key: "SUBQ", on: fp.has_subquery },
    { key: "HAVING", on: fp.has_having },
    { key: "ORDER", on: fp.has_order_by },
    { key: "DISTINCT", on: fp.has_distinct },
    { key: "LIMIT", on: fp.has_limit },
  ];
  const activeFlags = flags.filter((f) => f.on);
  if (!activeFlags.length)
    return <span className="text-gray-400 text-[10px]">simple</span>;
  return (
    <div className="flex flex-wrap gap-0.5">
      {activeFlags.map((f) => (
        <Badge key={f.key} variant="purple">
          {f.key}
        </Badge>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Query Detail (expandable row)
// ---------------------------------------------------------------------------
function QueryDetail({ fp }: { fp: Fingerprint }) {
  const [activeSection, setActiveSection] = useState("sql");
  const sections = [
    { id: "sql", label: "SQL", icon: Braces },
    {
      id: "tables",
      label: "Tables",
      icon: Table2,
      count: fp.tables.length,
    },
    {
      id: "columns",
      label: "Columns",
      icon: Columns3,
      count: fp.qualified_columns?.length || 0,
    },
    {
      id: "joins",
      label: "Joins",
      icon: GitBranch,
      count: fp.join_graph?.length || 0,
    },
    {
      id: "filters",
      label: "WHERE",
      icon: Filter,
      count: fp.where_conditions?.length || 0,
    },
    {
      id: "agg",
      label: "Group/Agg",
      icon: BarChart3,
      count: (fp.group_by?.length || 0) + (fp.functions?.length || 0),
    },
    {
      id: "patterns",
      label: "Patterns",
      icon: Layers,
      count:
        (fp.case_when_blocks?.length || 0) +
        (fp.window_exprs?.length || 0),
    },
  ];

  return (
    <motion.div
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: "auto", opacity: 1 }}
      exit={{ height: 0, opacity: 0 }}
      transition={{ duration: 0.3, ease: "easeInOut" }}
      className="overflow-hidden"
    >
      <div className="border-t border-gray-100 bg-gray-50 p-4 space-y-3">
        {/* Section tabs */}
        <div className="flex gap-1 overflow-x-auto pb-1">
          {sections.map((s) => (
            <button
              key={s.id}
              onClick={() => setActiveSection(s.id)}
              className={`
                flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap
                transition-all duration-200
                ${
                  activeSection === s.id
                    ? "bg-violet-600 text-white shadow-md"
                    : "bg-white hover:bg-gray-100 text-gray-500 hover:text-gray-700 border border-gray-200"
                }
              `}
            >
              <s.icon className="h-3 w-3" />
              {s.label}
              {s.count !== undefined && s.count > 0 && (
                <span
                  className={`
                  text-[9px] px-1 rounded-full
                  ${
                    activeSection === s.id
                      ? "bg-white/20"
                      : "bg-gray-200"
                  }
                `}
                >
                  {s.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Section content */}
        <AnimatePresence mode="wait">
          <motion.div
            key={activeSection}
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -5 }}
            transition={{ duration: 0.15 }}
          >
            {activeSection === "sql" && (
              <div className="rounded-lg bg-white border border-gray-200 p-3">
                <pre className="text-xs font-mono text-gray-700 whitespace-pre-wrap break-all leading-relaxed max-h-[300px] overflow-y-auto">
                  {fp.raw_sql || fp.canonical_sql}
                </pre>
              </div>
            )}

            {activeSection === "tables" && (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {fp.tables.map((t) => (
                  <div
                    key={t}
                    className="bg-white border border-gray-200 rounded-lg px-3 py-2 flex items-center gap-2"
                  >
                    <Table2 className="h-3.5 w-3.5 text-blue-500 flex-shrink-0" />
                    <span className="text-xs font-mono truncate text-gray-700">
                      {t}
                    </span>
                  </div>
                ))}
                {fp.alias_map &&
                  Object.keys(fp.alias_map).length > 0 && (
                    <div className="col-span-full mt-2">
                      <div className="text-[10px] text-gray-500 font-semibold uppercase tracking-wider mb-1">
                        Aliases
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {Object.entries(fp.alias_map).map(
                          ([alias, table]) => (
                            <Badge key={alias} variant="blue">
                              {alias} &rarr; {table}
                            </Badge>
                          )
                        )}
                      </div>
                    </div>
                  )}
              </div>
            )}

            {activeSection === "columns" && (
              <div className="space-y-2">
                {fp.qualified_columns && fp.qualified_columns.length > 0 ? (
                  Object.entries(
                    fp.qualified_columns.reduce(
                      (acc, [table, col]) => {
                        if (!acc[table]) acc[table] = [];
                        acc[table].push(col);
                        return acc;
                      },
                      {} as Record<string, string[]>
                    )
                  ).map(([table, cols]) => (
                    <div
                      key={table}
                      className="bg-white border border-gray-200 rounded-lg p-3"
                    >
                      <div className="text-[10px] text-gray-500 font-semibold uppercase tracking-wider mb-1.5">
                        {table}
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {cols.map((col, i) => (
                          <Badge key={`${col}-${i}`} variant="green">
                            {col}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-xs text-gray-400 text-center py-4">
                    No column data
                  </div>
                )}
                {fp.select_col_count > 0 && (
                  <div className="text-[10px] text-gray-400 text-right">
                    {fp.select_col_count} SELECT columns
                  </div>
                )}
              </div>
            )}

            {activeSection === "joins" && (
              <div className="space-y-2">
                {!fp.join_graph?.length ? (
                  <div className="text-xs text-gray-400 text-center py-4">
                    No joins in this query
                  </div>
                ) : (
                  fp.join_graph.map((j, i) => (
                    <div
                      key={i}
                      className="bg-white border border-gray-200 rounded-lg p-3 space-y-1.5"
                    >
                      <div className="flex items-center gap-2">
                        <Badge variant="blue">
                          {j.join_type || "JOIN"}
                        </Badge>
                        <span className="text-xs font-mono font-bold text-gray-700">
                          {j.left}
                        </span>
                        <GitBranch className="h-3 w-3 text-gray-400 rotate-90" />
                        <span className="text-xs font-mono font-bold text-gray-700">
                          {j.right}
                        </span>
                      </div>
                      {j.on_condition && (
                        <div className="text-[11px] font-mono text-gray-500 bg-gray-50 rounded px-2 py-1">
                          ON {j.on_condition}
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            )}

            {activeSection === "filters" && (
              <div className="space-y-2">
                {!fp.where_conditions?.length ? (
                  <div className="text-xs text-gray-400 text-center py-4">
                    No WHERE conditions
                  </div>
                ) : (
                  fp.where_conditions.map((w, i) => (
                    <div
                      key={i}
                      className="bg-white border border-gray-200 rounded-lg px-3 py-2"
                    >
                      <span className="text-xs font-mono text-gray-700">
                        {w}
                      </span>
                    </div>
                  ))
                )}
                {fp.having_conditions && fp.having_conditions.length > 0 && (
                  <>
                    <div className="text-[10px] text-gray-500 font-semibold uppercase tracking-wider mt-3">
                      HAVING
                    </div>
                    {fp.having_conditions.map((h, i) => (
                      <div
                        key={i}
                        className="bg-white border border-gray-200 rounded-lg px-3 py-2"
                      >
                        <span className="text-xs font-mono text-gray-700">
                          {h}
                        </span>
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}

            {activeSection === "agg" && (
              <div className="space-y-3">
                {fp.functions && fp.functions.length > 0 && (
                  <div>
                    <div className="text-[10px] text-gray-500 font-semibold uppercase tracking-wider mb-1.5">
                      Functions
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {fp.functions.map((f, i) => (
                        <Badge key={`${f}-${i}`} variant="amber">
                          {f}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
                {fp.group_by && fp.group_by.length > 0 && (
                  <div>
                    <div className="text-[10px] text-gray-500 font-semibold uppercase tracking-wider mb-1.5">
                      GROUP BY
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {fp.group_by.map((g, i) => (
                        <Badge key={`${g}-${i}`} variant="green">
                          {g}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
                {fp.order_by && fp.order_by.length > 0 && (
                  <div>
                    <div className="text-[10px] text-gray-500 font-semibold uppercase tracking-wider mb-1.5">
                      ORDER BY
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {fp.order_by.map((o, i) => (
                        <Badge key={`${o}-${i}`} variant="blue">
                          {o}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeSection === "patterns" && (
              <div className="space-y-3">
                {fp.case_when_blocks && fp.case_when_blocks.length > 0 && (
                  <div>
                    <div className="text-[10px] text-gray-500 font-semibold uppercase tracking-wider mb-1.5">
                      CASE WHEN Blocks
                    </div>
                    {fp.case_when_blocks.map((c, i) => (
                      <div
                        key={i}
                        className="bg-white border border-gray-200 rounded-lg px-3 py-2 mt-1"
                      >
                        <pre className="text-xs font-mono whitespace-pre-wrap max-h-[100px] overflow-y-auto text-gray-700">
                          {c}
                        </pre>
                      </div>
                    ))}
                  </div>
                )}
                {fp.window_exprs && fp.window_exprs.length > 0 && (
                  <div>
                    <div className="text-[10px] text-gray-500 font-semibold uppercase tracking-wider mb-1.5">
                      Window Expressions
                    </div>
                    {fp.window_exprs.map((w, i) => (
                      <div
                        key={i}
                        className="bg-white border border-gray-200 rounded-lg px-3 py-2 mt-1"
                      >
                        <span className="text-xs font-mono text-gray-700">
                          {w}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {(!fp.case_when_blocks || fp.case_when_blocks.length === 0) &&
                  (!fp.window_exprs || fp.window_exprs.length === 0) && (
                    <div className="text-xs text-gray-400 text-center py-4">
                      No CASE/WINDOW patterns
                    </div>
                  )}
                {fp.nl_question && (
                  <div>
                    <div className="text-[10px] text-gray-500 font-semibold uppercase tracking-wider mb-1.5">
                      Natural Language Question
                    </div>
                    <div className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-xs text-gray-700">
                      {fp.nl_question}
                    </div>
                  </div>
                )}
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Query Explorer (main component)
// ---------------------------------------------------------------------------
export function QueriesTab() {
  const fingerprints = useAnalysisDashboardStore((s) => s.fingerprints);
  const totalFingerprints = useAnalysisDashboardStore(
    (s) => s.totalFingerprints
  );
  const selectedTable = useAnalysisDashboardStore((s) => s.selectedTable);

  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [sorting, setSorting] = useState<SortingState>([
    { id: "frequency", desc: true },
  ]);
  const [globalFilter, setGlobalFilter] = useState("");

  // Filter by selected table
  const filtered = useMemo(() => {
    if (!selectedTable) return fingerprints;
    return fingerprints.filter((fp) => fp.tables.includes(selectedTable));
  }, [fingerprints, selectedTable]);

  const toggleRow = (id: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const columns = useMemo<ColumnDef<Fingerprint>[]>(
    () => [
      {
        id: "expand",
        header: "",
        size: 32,
        cell: ({ row }) => (
          <button
            onClick={(e) => {
              e.stopPropagation();
              toggleRow(row.original.id);
            }}
            className="p-1 hover:bg-gray-200 rounded transition-colors"
          >
            {expandedRows.has(row.original.id) ? (
              <ChevronDown className="h-3.5 w-3.5 text-gray-400" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 text-gray-400" />
            )}
          </button>
        ),
      },
      {
        accessorKey: "tables",
        header: "Tables",
        size: 180,
        cell: ({ row }) => (
          <div className="flex flex-wrap gap-0.5">
            {row.original.tables.slice(0, 3).map((t) => (
              <Badge key={t} variant="blue">
                {t}
              </Badge>
            ))}
            {row.original.tables.length > 3 && (
              <Badge variant="default">
                +{row.original.tables.length - 3}
              </Badge>
            )}
          </div>
        ),
      },
      {
        accessorKey: "frequency",
        header: "Freq",
        size: 60,
        cell: ({ row }) => (
          <div className="flex items-center gap-1">
            <Hash className="h-3 w-3 text-gray-400" />
            <span className="font-mono text-xs font-bold tabular-nums text-gray-700">
              {row.original.frequency}
            </span>
          </div>
        ),
      },
      {
        id: "complexity",
        header: "Complexity",
        size: 120,
        cell: ({ row }) => <StructuralFlags fp={row.original} />,
        sortingFn: (a, b) => {
          const flagCount = (fp: Fingerprint) =>
            [
              fp.has_cte,
              fp.has_window,
              fp.has_union,
              fp.has_case,
              fp.has_subquery,
              fp.has_having,
              fp.has_order_by,
              fp.has_distinct,
              fp.has_limit,
            ].filter(Boolean).length;
          return flagCount(a.original) - flagCount(b.original);
        },
      },
      {
        id: "components",
        header: "Components",
        size: 200,
        cell: ({ row }) => {
          const fp = row.original;
          return (
            <div className="flex items-center gap-2 text-[10px] text-gray-400">
              {fp.qualified_columns && fp.qualified_columns.length > 0 && (
                <span className="flex items-center gap-0.5">
                  <Columns3 className="h-3 w-3" />{" "}
                  {fp.qualified_columns.length}
                </span>
              )}
              {fp.join_graph && fp.join_graph.length > 0 && (
                <span className="flex items-center gap-0.5">
                  <GitBranch className="h-3 w-3" />{" "}
                  {fp.join_graph.length}
                </span>
              )}
              {fp.where_conditions && fp.where_conditions.length > 0 && (
                <span className="flex items-center gap-0.5">
                  <Filter className="h-3 w-3" />{" "}
                  {fp.where_conditions.length}
                </span>
              )}
              {fp.functions && fp.functions.length > 0 && (
                <span className="flex items-center gap-0.5">
                  <BarChart3 className="h-3 w-3" />{" "}
                  {fp.functions.length}
                </span>
              )}
            </div>
          );
        },
      },
      {
        id: "preview",
        header: "SQL Preview",
        size: 300,
        cell: ({ row }) => (
          <div className="text-xs font-mono text-gray-400 truncate max-w-[300px]">
            {(
              row.original.raw_sql ||
              row.original.canonical_sql ||
              ""
            ).slice(0, 80)}
            {(
              row.original.raw_sql ||
              row.original.canonical_sql ||
              ""
            ).length > 80
              ? "..."
              : ""}
          </div>
        ),
      },
    ],
    [expandedRows]
  );

  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 25 } },
  });

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-gray-500">Query Explorer</h3>
      <p className="text-xs text-gray-400">
        Browse all extracted query fingerprints. Expand any row to see full
        component breakdown.
      </p>

      {!fingerprints.length ? (
        <div className="h-[400px] flex items-center justify-center text-sm text-gray-400">
          No fingerprints loaded
        </div>
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="space-y-3"
        >
          {/* Search + stats */}
          <div className="flex items-center gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input
                value={globalFilter}
                onChange={(e) => setGlobalFilter(e.target.value)}
                placeholder="Search queries by table, SQL content..."
                className="w-full pl-9 pr-3 py-2 rounded-lg border border-gray-200 bg-white text-sm placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-violet-300"
              />
            </div>
            <div className="text-xs text-gray-400 whitespace-nowrap">
              {table.getFilteredRowModel().rows.length} of{" "}
              {totalFingerprints} queries
              {selectedTable && (
                <span className="ml-2">
                  (filtered:{" "}
                  <Badge variant="blue">{selectedTable}</Badge>)
                </span>
              )}
            </div>
          </div>

          {/* Table */}
          <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  {table.getHeaderGroups().map((hg) => (
                    <tr
                      key={hg.id}
                      className="border-b border-gray-100 bg-gray-50"
                    >
                      {hg.headers.map((header) => (
                        <th
                          key={header.id}
                          className="px-3 py-2.5 text-left text-[10px] font-semibold text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700 transition-colors"
                          style={{ width: header.getSize() }}
                          onClick={header.column.getToggleSortingHandler()}
                        >
                          <div className="flex items-center gap-1">
                            {flexRender(
                              header.column.columnDef.header,
                              header.getContext()
                            )}
                            {header.column.getCanSort() && (
                              <ArrowUpDown className="h-3 w-3 opacity-50" />
                            )}
                          </div>
                        </th>
                      ))}
                    </tr>
                  ))}
                </thead>
                <tbody>
                  {table.getRowModel().rows.map((row) => (
                    <Fragment key={row.id}>
                      <tr
                        className={`
                          border-b border-gray-50 hover:bg-gray-50 cursor-pointer transition-colors
                          ${
                            expandedRows.has(row.original.id)
                              ? "bg-violet-50/30"
                              : ""
                          }
                        `}
                        onClick={() => toggleRow(row.original.id)}
                      >
                        {row.getVisibleCells().map((cell) => (
                          <td
                            key={cell.id}
                            className="px-3 py-2.5"
                            style={{ width: cell.column.getSize() }}
                          >
                            {flexRender(
                              cell.column.columnDef.cell,
                              cell.getContext()
                            )}
                          </td>
                        ))}
                      </tr>
                      <AnimatePresence>
                        {expandedRows.has(row.original.id) && (
                          <tr>
                            <td colSpan={columns.length}>
                              <QueryDetail fp={row.original} />
                            </td>
                          </tr>
                        )}
                      </AnimatePresence>
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between border-t border-gray-100 px-4 py-3 bg-gray-50">
              <div className="text-xs text-gray-400">
                Page {table.getState().pagination.pageIndex + 1} of{" "}
                {table.getPageCount()}
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => table.setPageIndex(0)}
                  disabled={!table.getCanPreviousPage()}
                  className="p-1.5 rounded hover:bg-gray-200 disabled:opacity-30 transition-colors"
                >
                  <ChevronsLeft className="h-4 w-4" />
                </button>
                <button
                  onClick={() => table.previousPage()}
                  disabled={!table.getCanPreviousPage()}
                  className="p-1.5 rounded hover:bg-gray-200 disabled:opacity-30 transition-colors"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <button
                  onClick={() => table.nextPage()}
                  disabled={!table.getCanNextPage()}
                  className="p-1.5 rounded hover:bg-gray-200 disabled:opacity-30 transition-colors"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
                <button
                  onClick={() =>
                    table.setPageIndex(table.getPageCount() - 1)
                  }
                  disabled={!table.getCanNextPage()}
                  className="p-1.5 rounded hover:bg-gray-200 disabled:opacity-30 transition-colors"
                >
                  <ChevronsRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </div>
  );
}
