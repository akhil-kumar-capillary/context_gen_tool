"use client";

import { useCallback, useMemo, useEffect, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  type Node,
  type Edge,
  Handle,
  Position,
  Panel,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ResponsiveHeatMap } from "@nivo/heatmap";
import { motion, AnimatePresence } from "framer-motion";
import { useAnalysisDashboardStore } from "@/stores/analysis-dashboard-store";

const DEFAULT_MAX_EDGES = 30;
const MAX_EDGES_OPTIONS = [15, 30, 50, 75];

interface JoinEdgeInfo {
  left: string;
  right: string;
  joinType: string;
  condition: string;
  count: number;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Custom Table Node
// ---------------------------------------------------------------------------
function TableNode({
  data,
}: {
  data: { label: string; count: number; selected: boolean };
}) {
  return (
    <div
      className={`
        px-4 py-3 rounded-xl border-2 shadow-lg backdrop-blur-sm
        transition-all duration-200 cursor-pointer select-none
        ${
          data.selected
            ? "border-primary bg-primary/5 shadow-primary/20 shadow-xl ring-2 ring-primary/30"
            : "border-border bg-background hover:border-primary/30 hover:shadow-xl hover:scale-105"
        }
      `}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-primary !w-2 !h-2 !border-0"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-primary !w-2 !h-2 !border-0"
      />
      <Handle
        type="target"
        position={Position.Left}
        className="!bg-primary !w-2 !h-2 !border-0"
      />
      <Handle
        type="source"
        position={Position.Right}
        className="!bg-primary !w-2 !h-2 !border-0"
      />
      <div className="text-xs font-mono font-bold text-foreground truncate max-w-[120px]">
        {data.label}
      </div>
      <div className="text-xs text-muted-foreground mt-0.5">
        {data.count} references
      </div>
    </div>
  );
}

const nodeTypes = { tableNode: TableNode };

// ---------------------------------------------------------------------------
// Join Graph
// ---------------------------------------------------------------------------
function JoinGraph() {
  const counters = useAnalysisDashboardStore((s) => s.counters);
  const selectedTable = useAnalysisDashboardStore((s) => s.selectedTable);
  const setSelectedTable = useAnalysisDashboardStore(
    (s) => s.setSelectedTable
  );
  const [hoveredEdge, setHoveredEdge] = useState<string | null>(null);
  const [selectedEdgeInfo, setSelectedEdgeInfo] =
    useState<JoinEdgeInfo | null>(null);
  const [maxEdges, setMaxEdges] = useState(DEFAULT_MAX_EDGES);

  const totalJoinPairs = counters?.join_pair?.length ?? 0;
  const totalTablesInData = useMemo(() => {
    if (!counters?.join_pair?.length) return 0;
    const tables = new Set<string>();
    for (const [pair] of counters.join_pair) {
      const pairArr = Array.isArray(pair) ? pair : String(pair).split(",");
      if (pairArr[0]) tables.add(String(pairArr[0]));
      if (pairArr[1]) tables.add(String(pairArr[1]));
    }
    return tables.size;
  }, [counters]);

  const joinEdges = useMemo<JoinEdgeInfo[]>(() => {
    if (!counters?.join_pair?.length) return [];
    const condMap = new Map<string, string>();
    if (counters.join_cond) {
      for (const [cond] of counters.join_cond) {
        const condArr = Array.isArray(cond) ? cond : [];
        if (condArr.length >= 3) {
          condMap.set(`${condArr[0]}|${condArr[1]}`, String(condArr[2]));
        }
      }
    }
    const limitedPairs = counters.join_pair.slice(0, maxEdges);
    return limitedPairs
      .map(([pair, count]) => {
        const pairArr = Array.isArray(pair) ? pair : String(pair).split(",");
        const left = String(pairArr[0] || "").trim();
        const right =
          pairArr.length > 1 ? String(pairArr[1] || "").trim() : "";
        if (!left || !right || left === right) return null;
        const condition =
          condMap.get(`${left}|${right}`) ||
          condMap.get(`${right}|${left}`) ||
          "";
        return { left, right, joinType: "JOIN", condition, count: count as number };
      })
      .filter((e): e is JoinEdgeInfo => e !== null);
  }, [counters, maxEdges]);

  const tableCounts = useMemo(() => {
    const map = new Map<string, number>();
    if (counters?.table) {
      for (const [name, count] of counters.table) {
        map.set(String(name), count as number);
      }
    }
    return map;
  }, [counters]);

  const allTables = useMemo(() => {
    const tables = new Set<string>();
    for (const edge of joinEdges) {
      tables.add(edge.left);
      if (edge.right) tables.add(edge.right);
    }
    return Array.from(tables);
  }, [joinEdges]);

  const { initialNodes, initialEdges } = useMemo(() => {
    const n = allTables.length;
    if (n === 0) return { initialNodes: [], initialEdges: [] };

    const radius = Math.max(200, n * 40);
    const centerX = 400;
    const centerY = 300;

    const nodes: Node[] = allTables.map((table, i) => {
      const angle = (2 * Math.PI * i) / n - Math.PI / 2;
      return {
        id: table,
        type: "tableNode",
        position: {
          x: centerX + radius * Math.cos(angle),
          y: centerY + radius * Math.sin(angle),
        },
        data: {
          label: table,
          count: tableCounts.get(table) || 0,
          selected: selectedTable === table,
        },
      };
    });

    const maxCount = Math.max(...joinEdges.map((e) => e.count), 1);
    const edges: Edge[] = joinEdges.map((je, i) => ({
      id: `edge-${i}`,
      source: je.left,
      target: je.right,
      type: "default",
      animated: hoveredEdge === `edge-${i}`,
      style: {
        stroke:
          hoveredEdge === `edge-${i}` ? "rgb(124, 58, 237)" : "#9ca3af",
        strokeWidth: Math.max(1.5, (je.count / maxCount) * 6),
        opacity: selectedTable
          ? je.left === selectedTable || je.right === selectedTable
            ? 1
            : 0.15
          : 0.7,
        transition: "all 0.3s ease",
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 12,
        height: 12,
        color: hoveredEdge === `edge-${i}` ? "rgb(124, 58, 237)" : "#9ca3af",
      },
      label: je.count > 1 ? `×${je.count}` : undefined,
      labelStyle: { fontSize: 10, fontWeight: 600, fill: "#111" },
      labelBgStyle: { fill: "#fff", fillOpacity: 0.9 },
      data: je,
    }));

    return { initialNodes: nodes, initialEdges: edges };
  }, [allTables, joinEdges, tableCounts, selectedTable, hoveredEdge]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      setSelectedTable(selectedTable === node.id ? null : node.id);
      setSelectedEdgeInfo(null);
    },
    [selectedTable, setSelectedTable]
  );

  const onEdgeClick = useCallback((_: React.MouseEvent, edge: Edge) => {
    const je = edge.data as unknown as JoinEdgeInfo;
    setSelectedEdgeInfo(je);
  }, []);

  const onEdgeMouseEnter = useCallback((_: React.MouseEvent, edge: Edge) => {
    setHoveredEdge(edge.id);
  }, []);

  const onEdgeMouseLeave = useCallback(() => {
    setHoveredEdge(null);
  }, []);

  if (!joinEdges.length) {
    return (
      <div className="h-[500px] flex items-center justify-center text-sm text-muted-foreground">
        No join relationships found
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5 }}
      className="h-[500px] w-full rounded-xl border border-border bg-muted/50 overflow-hidden relative"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onEdgeClick={onEdgeClick}
        onEdgeMouseEnter={onEdgeMouseEnter}
        onEdgeMouseLeave={onEdgeMouseLeave}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        minZoom={0.2}
        maxZoom={3}
      >
        <Background gap={20} size={1} color="#e5e7eb" />
        <Controls className="!bg-background !border-border !shadow-lg !rounded-lg [&>button]:!bg-background [&>button]:!border-border [&>button]:!fill-foreground [&>button:hover]:!bg-muted/50" />
        {allTables.length <= 50 && (
          <MiniMap
            nodeColor={() => "rgb(124, 58, 237)"}
            maskColor="rgba(0,0,0,0.1)"
            className="!bg-background !border-border !rounded-lg"
          />
        )}

        <Panel position="top-left" className="!m-2">
          <div className="bg-background/90 backdrop-blur-md border border-border rounded-lg px-3 py-2 space-y-1.5">
            <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Join Network
            </div>
            <div className="text-xs text-muted-foreground">
              {allTables.length === totalTablesInData
                ? `${allTables.length} tables`
                : `Showing ${allTables.length} of ${totalTablesInData} tables`}
              {" · "}
              {joinEdges.length === totalJoinPairs
                ? `${joinEdges.length} join pairs`
                : `${joinEdges.length} of ${totalJoinPairs} join pairs`}
            </div>
            {totalJoinPairs > MAX_EDGES_OPTIONS[0] && (
              <div className="flex items-center gap-1.5 pt-0.5">
                <span className="text-xs text-muted-foreground">Show:</span>
                {MAX_EDGES_OPTIONS.filter(
                  (n) => n <= totalJoinPairs + 10
                ).map((n) => (
                  <button
                    key={n}
                    onClick={() => setMaxEdges(n)}
                    className={`text-xs px-1.5 py-0.5 rounded transition-colors ${
                      maxEdges === n
                        ? "bg-primary/10 text-primary font-semibold"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted"
                    }`}
                  >
                    {n}
                  </button>
                ))}
                {totalJoinPairs >
                  MAX_EDGES_OPTIONS[MAX_EDGES_OPTIONS.length - 1] && (
                  <button
                    onClick={() =>
                      setMaxEdges(Math.min(totalJoinPairs, 200))
                    }
                    className={`text-xs px-1.5 py-0.5 rounded transition-colors ${
                      maxEdges >= Math.min(totalJoinPairs, 200)
                        ? "bg-primary/10 text-primary font-semibold"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted"
                    }`}
                  >
                    All{totalJoinPairs > 200 ? " (200)" : ""}
                  </button>
                )}
              </div>
            )}
            <div className="text-xs text-muted-foreground">
              Click node to filter · Click edge for details
            </div>
          </div>
        </Panel>
      </ReactFlow>

      <AnimatePresence>
        {selectedEdgeInfo && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="absolute bottom-3 left-3 right-3 z-10 bg-background/95 backdrop-blur-md border border-border rounded-xl p-4 shadow-2xl"
          >
            <div className="flex items-start justify-between">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-bold text-primary">
                    {selectedEdgeInfo.left}
                  </span>
                  <span className="text-xs text-muted-foreground">&rarr;</span>
                  <span className="font-mono text-sm font-bold text-primary">
                    {selectedEdgeInfo.right}
                  </span>
                </div>
                {selectedEdgeInfo.condition && (
                  <div className="text-xs text-muted-foreground font-mono bg-muted/50 rounded px-2 py-1">
                    ON {selectedEdgeInfo.condition}
                  </div>
                )}
                <div className="text-xs text-muted-foreground">
                  {selectedEdgeInfo.count} occurrence
                  {selectedEdgeInfo.count !== 1 ? "s" : ""}
                </div>
              </div>
              <button
                onClick={() => setSelectedEdgeInfo(null)}
                className="text-muted-foreground hover:text-foreground text-sm p-1"
              >
                ✕
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Column Heatmap
// ---------------------------------------------------------------------------
function ColumnHeatmap() {
  const counters = useAnalysisDashboardStore((s) => s.counters);
  const selectedTable = useAnalysisDashboardStore((s) => s.selectedTable);

  const data = useMemo(() => {
    if (!counters?.column?.length) return [];

    const tableColMap = new Map<string, Map<string, number>>();

    for (const [entry, count] of counters.column) {
      const entryStr = String(entry);
      let table = "*";
      let col = entryStr;
      if (entryStr.includes(".")) {
        const parts = entryStr.split(".");
        table = parts[0];
        col = parts.slice(1).join(".");
      }
      if (selectedTable && table !== selectedTable && table !== "*") continue;

      if (!tableColMap.has(table)) tableColMap.set(table, new Map());
      const colMap = tableColMap.get(table)!;
      colMap.set(col, (colMap.get(col) || 0) + (count as number));
    }

    const sortedTables = Array.from(tableColMap.entries())
      .sort((a, b) => {
        const sumA = Array.from(a[1].values()).reduce((s, v) => s + v, 0);
        const sumB = Array.from(b[1].values()).reduce((s, v) => s + v, 0);
        return sumB - sumA;
      })
      .slice(0, 15);

    const globalColCounts = new Map<string, number>();
    for (const [, colMap] of sortedTables) {
      for (const [col, cnt] of colMap) {
        globalColCounts.set(col, (globalColCounts.get(col) || 0) + cnt);
      }
    }
    const topCols = Array.from(globalColCounts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 20)
      .map(([col]) => col);

    return sortedTables.map(([table, colMap]) => ({
      id: table,
      data: topCols.map((col) => ({
        x: col,
        y: colMap.get(col) || 0,
      })),
    }));
  }, [counters, selectedTable]);

  if (!data.length) {
    return (
      <div className="h-[400px] flex items-center justify-center text-sm text-muted-foreground">
        No column data available
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="h-[400px] w-full"
    >
      <ResponsiveHeatMap
        data={data}
        margin={{ top: 70, right: 20, bottom: 30, left: 100 }}
        axisTop={{ tickSize: 0, tickPadding: 8, tickRotation: -45 }}
        axisLeft={{ tickSize: 0, tickPadding: 8 }}
        colors={{ type: "sequential", scheme: "blue_green", minValue: 0 }}
        emptyColor="#f3f4f6"
        borderWidth={1}
        borderColor="#e5e7eb"
        enableLabels
        labelTextColor={{ from: "color", modifiers: [["darker", 3]] }}
        hoverTarget="cell"
        motionConfig="gentle"
        theme={{
          axis: {
            ticks: {
              text: { fontSize: 10, fontFamily: "monospace", fill: "#6b7280" },
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
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Schema Tab (composed)
// ---------------------------------------------------------------------------
export function SchemaTab() {
  const selectedTable = useAnalysisDashboardStore((s) => s.selectedTable);

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h3 className="text-sm font-medium text-muted-foreground">
          Join Relationship Network
        </h3>
        <p className="text-xs text-muted-foreground">
          Drag nodes to rearrange. Click a node to filter. Click an edge for
          join conditions. Edge thickness = frequency.
        </p>
        <JoinGraph />
      </div>

      <div className="space-y-2">
        <h3 className="text-sm font-medium text-muted-foreground">
          Column × Table Heatmap
          {selectedTable && (
            <span className="ml-2 text-primary font-mono">
              (filtered: {selectedTable})
            </span>
          )}
        </h3>
        <p className="text-xs text-muted-foreground">
          Darker cells indicate higher column usage frequency
        </p>
        <div className="rounded-xl border border-border bg-background p-2">
          <ColumnHeatmap />
        </div>
      </div>
    </div>
  );
}
