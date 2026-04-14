"use client";

import { useMemo, useState } from "react";
import { ResponsiveSunburst } from "@nivo/sunburst";
import { motion, AnimatePresence } from "framer-motion";
import {
  useAnalysisDashboardStore,
  type Cluster,
} from "@/stores/analysis-dashboard-store";

interface TableGroupInfo {
  table: string;
  clusters: Cluster[];
  totalQueries: number;
  totalUnique: number;
}

type Selection =
  | { type: "cluster"; data: Cluster }
  | { type: "tableGroup"; data: TableGroupInfo };

// ---------------------------------------------------------------------------
// Cluster Detail Panel
// ---------------------------------------------------------------------------
function ClusterDetail({
  cluster,
  onClose,
}: {
  cluster: Cluster;
  onClose: () => void;
}) {
  return (
    <motion.div
      key={`cluster-${cluster.sig}`}
      initial={{ opacity: 0, x: 10 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -10 }}
      className="rounded-xl border border-border bg-background p-4 space-y-3"
    >
      <div className="flex items-start justify-between">
        <div>
          <h4 className="text-sm font-semibold text-foreground">
            Cluster: {cluster.sig}
          </h4>
          <p className="text-xs text-muted-foreground mt-0.5">
            {cluster.count} queries · {cluster.n_unique} unique patterns
          </p>
        </div>
        <button
          onClick={onClose}
          className="text-muted-foreground hover:text-foreground text-sm p-1"
        >
          ✕
        </button>
      </div>

      {cluster.tables.length > 0 && (
        <div>
          <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider mb-1">
            Tables
          </div>
          <div className="flex flex-wrap gap-1">
            {cluster.tables.map((t) => (
              <span
                key={t}
                className="px-1.5 py-0.5 rounded text-xs font-medium bg-primary/5 text-primary border border-primary/20"
              >
                {t}
              </span>
            ))}
          </div>
        </div>
      )}

      {cluster.functions.length > 0 && (
        <div>
          <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider mb-1">
            Functions
          </div>
          <div className="flex flex-wrap gap-1">
            {cluster.functions.map((f, i) => (
              <span
                key={`${f}-${i}`}
                className="px-1.5 py-0.5 rounded text-xs font-medium bg-amber-50 text-amber-600 border border-amber-200"
              >
                {f}
              </span>
            ))}
          </div>
        </div>
      )}

      {cluster.where.length > 0 && (
        <div>
          <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider mb-1">
            WHERE Conditions
          </div>
          <div className="space-y-1">
            {cluster.where.slice(0, 5).map((w, i) => (
              <div
                key={i}
                className="text-xs font-mono text-muted-foreground bg-muted/50 rounded px-2 py-1"
              >
                {w}
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider mb-1">
          Representative SQL
        </div>
        <pre className="text-xs font-mono text-foreground bg-muted/50 rounded-lg border border-border p-3 whitespace-pre-wrap break-all max-h-[150px] overflow-y-auto leading-relaxed">
          {cluster.rep_sql}
        </pre>
      </div>

      {cluster.cpx_sql && cluster.cpx_sql !== cluster.rep_sql && (
        <div>
          <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider mb-1">
            Most Complex SQL
          </div>
          <pre className="text-xs font-mono text-foreground bg-muted/50 rounded-lg border border-border p-3 whitespace-pre-wrap break-all max-h-[150px] overflow-y-auto leading-relaxed">
            {cluster.cpx_sql}
          </pre>
        </div>
      )}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Table Group Detail Panel
// ---------------------------------------------------------------------------
function TableGroupDetail({
  group,
  onClose,
  onSelectCluster,
}: {
  group: TableGroupInfo;
  onClose: () => void;
  onSelectCluster: (c: Cluster) => void;
}) {
  const allFunctions = new Map<string, number>();
  const allWhere = new Map<string, number>();
  for (const c of group.clusters) {
    for (const f of c.functions)
      allFunctions.set(f, (allFunctions.get(f) || 0) + c.count);
    for (const w of c.where)
      allWhere.set(w, (allWhere.get(w) || 0) + c.count);
  }
  const topFunctions = Array.from(allFunctions.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10);
  const topWhere = Array.from(allWhere.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  return (
    <motion.div
      key={`table-${group.table}`}
      initial={{ opacity: 0, x: 10 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -10 }}
      className="rounded-xl border border-border bg-background p-4 space-y-3 max-h-[420px] overflow-y-auto"
    >
      <div className="flex items-start justify-between">
        <div>
          <h4 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-primary/5 text-primary border border-primary/20">
              TABLE
            </span>
            {group.table}
          </h4>
          <p className="text-xs text-muted-foreground mt-0.5">
            {group.totalQueries.toLocaleString()} queries ·{" "}
            {group.totalUnique.toLocaleString()} unique ·{" "}
            {group.clusters.length} clusters
          </p>
        </div>
        <button
          onClick={onClose}
          className="text-muted-foreground hover:text-foreground text-sm p-1"
        >
          ✕
        </button>
      </div>

      {topFunctions.length > 0 && (
        <div>
          <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider mb-1">
            Top Functions (across all clusters)
          </div>
          <div className="flex flex-wrap gap-1">
            {topFunctions.map(([f, cnt]) => (
              <span
                key={f}
                className="px-1.5 py-0.5 rounded text-xs font-medium bg-amber-50 text-amber-600 border border-amber-200"
              >
                {f}{" "}
                <span className="opacity-60">({cnt})</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {topWhere.length > 0 && (
        <div>
          <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider mb-1">
            Top WHERE Conditions
          </div>
          <div className="space-y-1">
            {topWhere.map(([w, cnt], i) => (
              <div
                key={i}
                className="text-xs font-mono text-muted-foreground bg-muted/50 rounded px-2 py-1 flex items-center justify-between"
              >
                <span className="truncate">{w}</span>
                <span className="text-xs ml-2 flex-shrink-0 opacity-60">
                  {cnt}x
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider mb-1">
          Clusters ({group.clusters.length})
        </div>
        <div className="space-y-1">
          {group.clusters
            .sort((a, b) => b.count - a.count)
            .slice(0, 15)
            .map((c, i) => (
              <button
                key={i}
                onClick={() => onSelectCluster(c)}
                className="w-full text-left px-2.5 py-2 rounded-md hover:bg-muted/50 transition-colors border border-transparent hover:border-border"
              >
                <div className="flex items-center justify-between">
                  <div className="text-xs font-mono truncate max-w-[180px] text-foreground">
                    {c.sig}
                  </div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground flex-shrink-0">
                    <span>{c.count} queries</span>
                    <span>{c.n_unique} unique</span>
                  </div>
                </div>
              </button>
            ))}
          {group.clusters.length > 15 && (
            <div className="text-xs text-muted-foreground text-center py-1">
              +{group.clusters.length - 15} more clusters
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Patterns Tab (Cluster Sunburst)
// ---------------------------------------------------------------------------
export function PatternsTab() {
  const clusters = useAnalysisDashboardStore((s) => s.clusters);
  const [selection, setSelection] = useState<Selection | null>(null);

  const { sunburstData, tableGroupMap } = useMemo(() => {
    if (!clusters?.length)
      return {
        sunburstData: null,
        tableGroupMap: new Map<string, Cluster[]>(),
      };

    const tableGroups = new Map<string, Cluster[]>();
    for (const c of clusters) {
      const primaryTable = c.tables?.[0] || "unknown";
      if (!tableGroups.has(primaryTable))
        tableGroups.set(primaryTable, []);
      tableGroups.get(primaryTable)!.push(c);
    }

    const sortedEntries = Array.from(tableGroups.entries())
      .sort((a, b) => {
        const sumA = a[1].reduce((s, c) => s + c.count, 0);
        const sumB = b[1].reduce((s, c) => s + c.count, 0);
        return sumB - sumA;
      })
      .slice(0, 20);

    return {
      sunburstData: {
        name: "clusters",
        children: sortedEntries.map(([table, clusterList]) => ({
          name: table,
          children: clusterList
            .sort((a, b) => b.count - a.count)
            .slice(0, 10)
            .map((c, i) => ({
              name: c.sig || `cluster-${i}`,
              value: c.count,
              cluster: c,
            })),
        })),
      },
      tableGroupMap: new Map(sortedEntries),
    };
  }, [clusters]);

  if (!sunburstData) {
    return (
      <div className="space-y-2">
        <h3 className="text-sm font-medium text-muted-foreground">Query Clusters</h3>
        <div className="h-[400px] flex items-center justify-center text-sm text-muted-foreground">
          No cluster data available
        </div>
      </div>
    );
  }

  const handleSunburstClick = (node: {
    id: string | number;
    data: Record<string, unknown>;
  }) => {
    const nodeData = node.data as {
      cluster?: Cluster;
      children?: unknown[];
    };
    if (nodeData.cluster) {
      setSelection({ type: "cluster", data: nodeData.cluster });
    } else if (nodeData.children) {
      const tableName = String(node.id);
      const groupClusters = tableGroupMap.get(tableName);
      if (groupClusters) {
        setSelection({
          type: "tableGroup",
          data: {
            table: tableName,
            clusters: groupClusters,
            totalQueries: groupClusters.reduce((s, c) => s + c.count, 0),
            totalUnique: groupClusters.reduce(
              (s, c) => s + c.n_unique,
              0
            ),
          },
        });
      }
    }
  };

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-muted-foreground">Query Clusters</h3>
      <p className="text-xs text-muted-foreground">
        Queries grouped by table signature. Click a segment to explore the
        cluster&apos;s representative and most complex SQL.
      </p>

      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4 }}
        className="space-y-4"
      >
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Sunburst Chart */}
          <div className="h-[420px] rounded-xl border border-border bg-background p-2">
            <ResponsiveSunburst
              data={sunburstData}
              id="name"
              value="value"
              margin={{ top: 10, right: 10, bottom: 10, left: 10 }}
              cornerRadius={4}
              borderWidth={2}
              borderColor="#fff"
              colors={{ scheme: "spectral" }}
              childColor={{ from: "color", modifiers: [["brighter", 0.3]] }}
              enableArcLabels
              arcLabel={(e) => {
                const label = String(e.id);
                return label.length > 12 ? label.slice(0, 12) + "..." : label;
              }}
              arcLabelsSkipAngle={15}
              arcLabelsTextColor={{
                from: "color",
                modifiers: [["darker", 3]],
              }}
              motionConfig="gentle"
              onClick={handleSunburstClick}
              theme={{
                labels: {
                  text: {
                    fontSize: 10,
                    fontWeight: 600,
                    fontFamily: "monospace",
                  },
                },
                tooltip: {
                  container: {
                    background: "#fff",
                    color: "#111",
                    borderRadius: "8px",
                    border: "1px solid #e5e7eb",
                    boxShadow: "0 8px 32px rgba(0,0,0,0.08)",
                    padding: "8px 12px",
                    fontSize: "12px",
                  },
                },
              }}
            />
          </div>

          {/* Details Panel */}
          <div className="space-y-3">
            <AnimatePresence mode="wait">
              {selection?.type === "cluster" ? (
                <ClusterDetail
                  cluster={selection.data}
                  onClose={() => setSelection(null)}
                />
              ) : selection?.type === "tableGroup" ? (
                <TableGroupDetail
                  group={selection.data}
                  onClose={() => setSelection(null)}
                  onSelectCluster={(c) =>
                    setSelection({ type: "cluster", data: c })
                  }
                />
              ) : (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="rounded-xl border border-border bg-muted/50 p-8 flex items-center justify-center h-[420px]"
                >
                  <div className="text-center space-y-2">
                    <p className="text-sm text-muted-foreground">
                      Click any segment to explore
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Inner ring = table groups · Outer ring = individual
                      clusters
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {clusters.length} clusters found
                    </p>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Cluster list */}
            <div className="rounded-xl border border-border bg-background overflow-hidden max-h-[300px] overflow-y-auto">
              {clusters.slice(0, 30).map((c, i) => (
                <button
                  key={i}
                  onClick={() =>
                    setSelection({ type: "cluster", data: c })
                  }
                  className={`
                    w-full text-left px-4 py-2.5 border-b border-border last:border-0 hover:bg-muted/50 transition-colors
                    ${
                      selection?.type === "cluster" &&
                      selection.data.sig === c.sig
                        ? "bg-primary/5"
                        : ""
                    }
                  `}
                >
                  <div className="flex items-center justify-between">
                    <div className="text-xs font-mono truncate max-w-[200px] text-foreground">
                      {c.sig}
                    </div>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <span>{c.count} queries</span>
                      <span>{c.n_unique} unique</span>
                      <span>{c.tables.length} tables</span>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
