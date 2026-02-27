"use client";

import { motion } from "framer-motion";
import { ResponsiveTreeMap } from "@nivo/treemap";
import { ResponsiveBar } from "@nivo/bar";
import { useAnalysisDashboardStore } from "@/stores/analysis-dashboard-store";
import { NIVO_TOOLTIP_THEME, NIVO_BAR_THEME } from "./shared";

// ---------------------------------------------------------------------------
// Table Treemap
// ---------------------------------------------------------------------------
function TableTreemap() {
  const counters = useAnalysisDashboardStore((s) => s.counters);
  const selectedTable = useAnalysisDashboardStore((s) => s.selectedTable);
  const setSelectedTable = useAnalysisDashboardStore(
    (s) => s.setSelectedTable
  );

  if (!counters?.table?.length) {
    return (
      <div className="h-[400px] flex items-center justify-center text-sm text-gray-400">
        No table data
      </div>
    );
  }

  const data = {
    name: "tables",
    children: counters.table.slice(0, 40).map(([name, count]) => ({
      name: String(name),
      count: count as number,
    })),
  };

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      className="h-[400px] w-full"
    >
      <ResponsiveTreeMap
        data={data}
        identity="name"
        value="count"
        valueFormat=" >-.0f"
        leavesOnly
        innerPadding={3}
        outerPadding={3}
        margin={{ top: 0, right: 0, bottom: 0, left: 0 }}
        label={(e) => `${e.id} (${e.formattedValue})`}
        labelSkipSize={40}
        labelTextColor={{ from: "color", modifiers: [["darker", 3]] }}
        borderWidth={2}
        borderColor={{ from: "color", modifiers: [["darker", 0.5]] }}
        colors={{ scheme: "blues" }}
        nodeOpacity={0.95}
        onClick={(node) => {
          const tableName = String(node.id);
          setSelectedTable(selectedTable === tableName ? null : tableName);
        }}
        motionConfig="gentle"
        theme={{
          labels: {
            text: { fontSize: 11, fontWeight: 600, fontFamily: "monospace" },
          },
          ...NIVO_TOOLTIP_THEME,
        }}
      />
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Function Bars
// ---------------------------------------------------------------------------
function FunctionBars() {
  const counters = useAnalysisDashboardStore((s) => s.counters);

  if (!counters?.function?.length) {
    return (
      <div className="h-[300px] flex items-center justify-center text-sm text-gray-400">
        No function data
      </div>
    );
  }

  const data = counters.function
    .slice(0, 20)
    .map(([name, count]) => ({
      id: String(name),
      value: count as number,
    }))
    .reverse();

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.4 }}
      className="h-[300px]"
    >
      <ResponsiveBar
        data={data}
        keys={["value"]}
        indexBy="id"
        layout="horizontal"
        margin={{ top: 5, right: 20, bottom: 30, left: 120 }}
        padding={0.3}
        colors={{ scheme: "purples" }}
        borderRadius={4}
        enableLabel
        label={(d) => `${d.value}`}
        labelTextColor={{ from: "color", modifiers: [["darker", 2]] }}
        enableGridX
        enableGridY={false}
        axisBottom={{ tickSize: 0, tickPadding: 8 }}
        axisLeft={{ tickSize: 0, tickPadding: 8 }}
        motionConfig="gentle"
        theme={NIVO_BAR_THEME}
      />
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Structural Bars
// ---------------------------------------------------------------------------
function StructuralBars() {
  const counters = useAnalysisDashboardStore((s) => s.counters);
  const totalWeight = useAnalysisDashboardStore((s) => s.totalWeight);

  if (!counters?.structural?.length) {
    return (
      <div className="h-[250px] flex items-center justify-center text-sm text-gray-400">
        No structural data
      </div>
    );
  }

  const data = counters.structural
    .map(([name, count]) => ({
      id: String(name).replace("has_", ""),
      value: count as number,
      pct:
        totalWeight > 0
          ? Math.round(((count as number) / totalWeight) * 100)
          : 0,
    }))
    .sort((a, b) => b.value - a.value);

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.4 }}
      className="h-[250px]"
    >
      <ResponsiveBar
        data={data}
        keys={["value"]}
        indexBy="id"
        layout="horizontal"
        margin={{ top: 5, right: 40, bottom: 30, left: 90 }}
        padding={0.35}
        colors={{ scheme: "oranges" }}
        borderRadius={4}
        enableLabel
        label={(d) =>
          `${data.find((x) => x.id === d.indexValue)?.pct || 0}%`
        }
        labelTextColor={{ from: "color", modifiers: [["darker", 2]] }}
        enableGridX
        enableGridY={false}
        axisBottom={{ tickSize: 0, tickPadding: 8 }}
        axisLeft={{ tickSize: 0, tickPadding: 8 }}
        motionConfig="gentle"
        theme={NIVO_BAR_THEME}
      />
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Overview Tab (composed)
// ---------------------------------------------------------------------------
export function OverviewTab() {
  return (
    <div className="space-y-6">
      {/* Treemap */}
      <div className="space-y-2">
        <h3 className="text-sm font-medium text-gray-500">Table Universe</h3>
        <p className="text-xs text-gray-400">
          Click any table to filter all visualizations
        </p>
        <TableTreemap />
      </div>

      {/* Side-by-side bars */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-gray-500">Top Functions</h3>
          <div className="rounded-xl border border-gray-200 bg-white p-3">
            <FunctionBars />
          </div>
        </div>
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-gray-500">
            Structural Features
          </h3>
          <div className="rounded-xl border border-gray-200 bg-white p-3">
            <StructuralBars />
          </div>
        </div>
      </div>
    </div>
  );
}
