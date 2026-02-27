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
  FileCode2,
  User,
  Calendar,
  Braces,
  CheckCircle2,
  XCircle,
  Briefcase,
  Clock,
  Hash,
  Code2,
} from "lucide-react";
import {
  useAnalysisDashboardStore,
  type NotebookMeta,
  type ExtractedSQL,
} from "@/stores/analysis-dashboard-store";
import { Badge, formatShortDate, abbreviatePath } from "./shared";




// ---------------------------------------------------------------------------
// NotebookRow — enriched type with computed valid_sql_count
// ---------------------------------------------------------------------------

interface NotebookRow extends NotebookMeta {
  valid_sql_count: number;
}

// ---------------------------------------------------------------------------
// SqlDetail — collapsible SQL cell list inside expanded notebook
// ---------------------------------------------------------------------------

function SqlDetail({ sqls }: { sqls: ExtractedSQL[] }) {
  const [expandedSql, setExpandedSql] = useState<number | null>(null);

  if (!sqls.length) {
    return (
      <div className="text-xs text-gray-400 text-center py-6">
        No SQL queries extracted from this notebook
      </div>
    );
  }

  const displayedSqls = sqls.slice(0, 50);

  return (
    <div className="space-y-1.5">
      {displayedSqls.map((sql, idx) => (
        <div
          key={`${sql.notebook_path}-${sql.cell_number}-${idx}`}
          className="rounded-lg border border-gray-200 bg-white overflow-hidden"
        >
          {/* SQL row header */}
          <button
            onClick={() => setExpandedSql(expandedSql === idx ? null : idx)}
            className="w-full flex items-center gap-3 px-3 py-2 hover:bg-gray-50 transition-colors text-left"
          >
            <div className="flex items-center gap-1.5 flex-shrink-0">
              {expandedSql === idx ? (
                <ChevronDown className="h-3 w-3 text-gray-400" />
              ) : (
                <ChevronRight className="h-3 w-3 text-gray-400" />
              )}
              <span className="text-[10px] font-mono text-gray-500 w-12">
                Cell {sql.cell_number}
              </span>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              {sql.is_valid ? (
                <Badge variant="green">Valid</Badge>
              ) : (
                <Badge variant="red">Invalid</Badge>
              )}
              {sql.language && <Badge variant="blue">{sql.language}</Badge>}
            </div>
            <div className="text-xs font-mono text-gray-400 truncate flex-1">
              {(sql.cleaned_sql || "").slice(0, 100)}
              {(sql.cleaned_sql || "").length > 100 ? "..." : ""}
            </div>
            {sql.sql_hash && (
              <span className="text-[9px] font-mono text-gray-300 flex-shrink-0">
                #{sql.sql_hash.slice(0, 8)}
              </span>
            )}
          </button>

          {/* Expanded SQL content */}
          <AnimatePresence>
            {expandedSql === idx && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2, ease: "easeInOut" }}
                className="overflow-hidden"
              >
                <div className="border-t border-gray-100 bg-gray-50 p-3 space-y-2">
                  <pre className="text-xs font-mono text-gray-700 whitespace-pre-wrap break-all leading-relaxed max-h-[300px] overflow-y-auto bg-white rounded-lg border border-gray-200 p-3">
                    {sql.cleaned_sql || "(empty)"}
                  </pre>
                  <div className="flex flex-wrap gap-3 text-[10px] text-gray-400">
                    {sql.org_id && (
                      <span className="flex items-center gap-1">
                        <Hash className="h-3 w-3" />
                        Org: {sql.org_id}
                      </span>
                    )}
                    {sql.file_type && (
                      <span className="flex items-center gap-1">
                        <FileCode2 className="h-3 w-3" />
                        {sql.file_type}
                      </span>
                    )}
                    {sql.sql_hash && (
                      <span className="flex items-center gap-1">
                        <Code2 className="h-3 w-3" />
                        Hash: {sql.sql_hash}
                      </span>
                    )}
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      ))}
      {sqls.length > 50 && (
        <div className="text-xs text-gray-400 text-center py-2 border border-gray-200 rounded-lg bg-gray-50">
          Showing 50 of {sqls.length} SQL queries
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// NotebookDetail — expanded row with metadata + SQL cells
// ---------------------------------------------------------------------------

function NotebookDetail({
  notebook,
  sqls,
}: {
  notebook: NotebookRow;
  sqls: ExtractedSQL[];
}) {
  return (
    <motion.div
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: "auto", opacity: 1 }}
      exit={{ height: 0, opacity: 0 }}
      transition={{ duration: 0.3, ease: "easeInOut" }}
      className="overflow-hidden"
    >
      <div className="border-t border-gray-100 bg-gray-50 p-4 space-y-4">
        {/* Notebook metadata grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-white border border-gray-200 rounded-lg px-3 py-2">
            <div className="text-[10px] text-gray-400 font-semibold uppercase tracking-wider">
              Full Path
            </div>
            <div className="text-xs font-mono text-gray-700 mt-1 break-all">
              {notebook.notebook_path}
            </div>
          </div>
          {notebook.user_name && (
            <div className="bg-white border border-gray-200 rounded-lg px-3 py-2">
              <div className="text-[10px] text-gray-400 font-semibold uppercase tracking-wider">
                Owner
              </div>
              <div className="text-xs text-gray-700 mt-1 flex items-center gap-1.5">
                <User className="h-3 w-3 text-blue-500" />
                {notebook.user_name}
              </div>
            </div>
          )}
          {notebook.nb_created_at && (
            <div className="bg-white border border-gray-200 rounded-lg px-3 py-2">
              <div className="text-[10px] text-gray-400 font-semibold uppercase tracking-wider">
                Created
              </div>
              <div className="text-xs text-gray-700 mt-1 flex items-center gap-1.5">
                <Calendar className="h-3 w-3 text-emerald-500" />
                {formatShortDate(notebook.nb_created_at)}
              </div>
            </div>
          )}
          {notebook.nb_modified_at && (
            <div className="bg-white border border-gray-200 rounded-lg px-3 py-2">
              <div className="text-[10px] text-gray-400 font-semibold uppercase tracking-wider">
                Modified
              </div>
              <div className="text-xs text-gray-700 mt-1 flex items-center gap-1.5">
                <Clock className="h-3 w-3 text-amber-500" />
                {formatShortDate(notebook.nb_modified_at)}
              </div>
            </div>
          )}
        </div>

        {/* Job info if attached */}
        {notebook.is_attached_to_jobs === "Yes" && (
          <div className="bg-white border border-gray-200 rounded-lg px-3 py-2">
            <div className="text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-1.5">
              Job Attachment
            </div>
            <div className="flex flex-wrap gap-2 text-xs">
              {notebook.job_name && (
                <Badge variant="cyan">
                  <Briefcase className="h-3 w-3 mr-1" />
                  {notebook.job_name}
                </Badge>
              )}
              {notebook.job_id && (
                <Badge variant="default">ID: {notebook.job_id}</Badge>
              )}
              {notebook.trigger_type && (
                <Badge variant="purple">{notebook.trigger_type}</Badge>
              )}
              {notebook.cont_success_run_count != null && (
                <Badge variant="green">
                  {notebook.cont_success_run_count} consecutive runs
                </Badge>
              )}
              {notebook.earliest_run_date && (
                <Badge variant="amber">
                  Since {notebook.earliest_run_date}
                </Badge>
              )}
            </div>
          </div>
        )}

        {/* Extracted SQL cells */}
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Braces className="h-4 w-4 text-gray-400" />
            <h4 className="text-sm font-medium text-gray-500">
              Extracted SQL Queries
            </h4>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-500">
              {sqls.length}
            </span>
          </div>
          <SqlDetail sqls={sqls} />
        </div>
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Main NotebooksTab
// ---------------------------------------------------------------------------

export function NotebooksTab() {
  const notebooks = useAnalysisDashboardStore((s) => s.notebooks);
  const extractedSqls = useAnalysisDashboardStore((s) => s.extractedSqls);

  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [sorting, setSorting] = useState<SortingState>([
    { id: "sql_count", desc: true },
  ]);
  const [globalFilter, setGlobalFilter] = useState("");

  // Group extracted SQLs by notebook path (once)
  const sqlByPath = useMemo(() => {
    const map = new Map<string, ExtractedSQL[]>();
    for (const sql of extractedSqls) {
      const arr = map.get(sql.notebook_path) || [];
      arr.push(sql);
      map.set(sql.notebook_path, arr);
    }
    return map;
  }, [extractedSqls]);

  // Build notebook rows with valid SQL counts derived from same source as sql_count
  const notebookRows = useMemo<NotebookRow[]>(() => {
    return notebooks.map((nb) => {
      const sqls = sqlByPath.get(nb.notebook_path) || [];
      // When we have extracted SQL data, use it for valid count;
      // cap at sql_count to never exceed 100%
      const valid = sqls.filter((s) => s.is_valid).length;
      return {
        ...nb,
        valid_sql_count: Math.min(valid, nb.sql_count),
      };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notebooks, sqlByPath]);

  // Get SQLs for a specific notebook (uses memoized map)
  const getSqlsForNotebook = (path: string): ExtractedSQL[] => {
    return (sqlByPath.get(path) || []).slice().sort((a, b) => a.cell_number - b.cell_number);
  };

  const toggleRow = (path: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const columns = useMemo<ColumnDef<NotebookRow>[]>(
    () => [
      {
        id: "expand",
        header: "",
        size: 32,
        cell: ({ row }) => (
          <button
            onClick={(e) => {
              e.stopPropagation();
              toggleRow(row.original.notebook_path);
            }}
            className="p-1 hover:bg-gray-100 rounded transition-colors"
          >
            {expandedRows.has(row.original.notebook_path) ? (
              <ChevronDown className="h-3.5 w-3.5 text-gray-400" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 text-gray-400" />
            )}
          </button>
        ),
      },
      {
        accessorKey: "notebook_name",
        header: "Notebook",
        size: 220,
        cell: ({ row }) => (
          <div className="space-y-0.5">
            <div className="text-xs font-medium text-gray-700 flex items-center gap-1.5">
              <FileCode2 className="h-3.5 w-3.5 text-blue-500 flex-shrink-0" />
              <span className="truncate">
                {row.original.notebook_name ||
                  row.original.notebook_path?.split("/").pop()}
              </span>
            </div>
            <div className="text-[10px] font-mono text-gray-400 truncate pl-5">
              {abbreviatePath(row.original.notebook_path)}
            </div>
          </div>
        ),
      },
      {
        accessorKey: "user_name",
        header: "User",
        size: 130,
        cell: ({ row }) => (
          <div className="text-xs text-gray-500 truncate">
            {row.original.user_name || "—"}
          </div>
        ),
      },
      {
        accessorKey: "language",
        header: "Language",
        size: 90,
        cell: ({ row }) =>
          row.original.language ? (
            <Badge variant="purple">{row.original.language}</Badge>
          ) : (
            <span className="text-[10px] text-gray-400">&mdash;</span>
          ),
      },
      {
        accessorKey: "sql_count",
        header: "SQLs",
        size: 70,
        cell: ({ row }) => (
          <div className="flex items-center gap-1.5">
            <Braces className="h-3 w-3 text-gray-400" />
            <span className="font-mono text-xs font-bold tabular-nums text-gray-700">
              {row.original.sql_count}
            </span>
          </div>
        ),
      },
      {
        accessorKey: "valid_sql_count",
        header: "Valid %",
        size: 70,
        cell: ({ row }) => {
          const { valid_sql_count, sql_count } = row.original;
          if (sql_count === 0)
            return <span className="text-[10px] text-gray-400">—</span>;
          const pct = Math.round((valid_sql_count / sql_count) * 100);
          return (
            <div className="flex items-center gap-1.5">
              {pct >= 80 ? (
                <CheckCircle2 className="h-3 w-3 text-emerald-500" />
              ) : pct >= 50 ? (
                <CheckCircle2 className="h-3 w-3 text-amber-500" />
              ) : (
                <XCircle className="h-3 w-3 text-red-500" />
              )}
              <span className="font-mono text-[10px] tabular-nums text-gray-600">
                {pct}%
              </span>
            </div>
          );
        },
        sortingFn: (a, b) => {
          const pctA = a.original.sql_count
            ? a.original.valid_sql_count / a.original.sql_count
            : 0;
          const pctB = b.original.sql_count
            ? b.original.valid_sql_count / b.original.sql_count
            : 0;
          return pctA - pctB;
        },
      },
      {
        accessorKey: "is_attached_to_jobs",
        header: "Job",
        size: 60,
        cell: ({ row }) =>
          row.original.is_attached_to_jobs === "Yes" ? (
            <Badge variant="cyan">
              <Briefcase className="h-3 w-3 mr-0.5" />
              Yes
            </Badge>
          ) : (
            <span className="text-[10px] text-gray-400">No</span>
          ),
      },
      {
        accessorKey: "nb_modified_at",
        header: "Modified",
        size: 110,
        cell: ({ row }) => (
          <div className="text-[10px] text-gray-500">
            {formatShortDate(row.original.nb_modified_at)}
          </div>
        ),
        sortingFn: (a, b) => {
          const aDate = a.original.nb_modified_at
            ? new Date(a.original.nb_modified_at).getTime()
            : 0;
          const bDate = b.original.nb_modified_at
            ? new Date(b.original.nb_modified_at).getTime()
            : 0;
          return aDate - bDate;
        },
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [expandedRows]
  );

  const table = useReactTable({
    data: notebookRows,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 25 } },
    globalFilterFn: (row, _columnId, filterValue: string) => {
      const s = filterValue.toLowerCase();
      const nb = row.original;
      return (
        (nb.notebook_name || "").toLowerCase().includes(s) ||
        nb.notebook_path.toLowerCase().includes(s) ||
        (nb.user_name || "").toLowerCase().includes(s) ||
        (nb.language || "").toLowerCase().includes(s) ||
        (nb.job_name || "").toLowerCase().includes(s)
      );
    },
  });

  // Stats
  const totalSqls = extractedSqls.length;
  const validSqls = extractedSqls.filter((s) => s.is_valid).length;
  const jobNotebooks = notebookRows.filter(
    (n) => n.is_attached_to_jobs === "Yes"
  ).length;

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-gray-500">Notebook Explorer</h3>
      <p className="text-xs text-gray-400">
        Browse all extracted notebooks with metadata. Expand any row to see
        owner, dates, job attachments, and all SQL queries extracted from that
        notebook.
      </p>

      {!notebooks.length ? (
        <div className="h-[400px] flex items-center justify-center text-sm text-gray-400">
          No notebook data available. Run extraction first.
        </div>
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="space-y-3"
        >
          {/* Summary stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="rounded-xl border border-gray-200 bg-white p-3">
              <p className="text-[10px] text-gray-500 font-semibold uppercase tracking-wider">
                Notebooks
              </p>
              <p className="text-xl font-bold tabular-nums mt-0.5 text-gray-900">
                {notebooks.length}
              </p>
            </div>
            <div className="rounded-xl border border-gray-200 bg-white p-3">
              <p className="text-[10px] text-gray-500 font-semibold uppercase tracking-wider">
                Total SQLs
              </p>
              <p className="text-xl font-bold tabular-nums mt-0.5 text-gray-900">
                {totalSqls}
              </p>
            </div>
            <div className="rounded-xl border border-gray-200 bg-white p-3">
              <p className="text-[10px] text-gray-500 font-semibold uppercase tracking-wider">
                Valid SQLs
              </p>
              <p className="text-xl font-bold tabular-nums mt-0.5 text-gray-900">
                {validSqls}
                <span className="text-xs font-normal text-gray-400 ml-1">
                  ({totalSqls > 0 ? Math.round((validSqls / totalSqls) * 100) : 0}
                  %)
                </span>
              </p>
            </div>
            <div className="rounded-xl border border-gray-200 bg-white p-3">
              <p className="text-[10px] text-gray-500 font-semibold uppercase tracking-wider">
                Job-Attached
              </p>
              <p className="text-xl font-bold tabular-nums mt-0.5 text-gray-900">
                {jobNotebooks}
                <span className="text-xs font-normal text-gray-400 ml-1">
                  notebooks
                </span>
              </p>
            </div>
          </div>

          {/* Search */}
          <div className="flex items-center gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input
                value={globalFilter}
                onChange={(e) => setGlobalFilter(e.target.value)}
                placeholder="Search notebooks by name, path, user, language..."
                className="w-full pl-9 pr-3 py-2 rounded-lg border border-gray-200 bg-white text-sm placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-violet-300"
              />
            </div>
            <div className="text-xs text-gray-400 whitespace-nowrap">
              {table.getFilteredRowModel().rows.length} of {notebooks.length}{" "}
              notebooks
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
                    <Fragment key={row.original.notebook_path}>
                      <tr
                        className={`
                          border-b border-gray-50 cursor-pointer transition-colors
                          ${
                            expandedRows.has(row.original.notebook_path)
                              ? "bg-violet-50/50"
                              : "hover:bg-gray-50"
                          }
                        `}
                        onClick={() => toggleRow(row.original.notebook_path)}
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
                        {expandedRows.has(row.original.notebook_path) && (
                          <tr>
                            <td colSpan={columns.length}>
                              <NotebookDetail
                                notebook={row.original}
                                sqls={getSqlsForNotebook(
                                  row.original.notebook_path
                                )}
                              />
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
