"use client";

import {
  ChevronDown,
  ChevronRight,
  Globe,
  Lock,
  Key,
  FileText,
  Paperclip,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  useContextEngineStore,
  type ContextTreeNode,
} from "@/stores/context-engine-store";

// ── Health badge colors ──

function healthColors(score: number) {
  if (score >= 80)
    return {
      bg: "bg-green-50",
      text: "text-green-700",
      dot: "bg-green-500",
    };
  if (score >= 60)
    return {
      bg: "bg-amber-50",
      text: "text-amber-700",
      dot: "bg-amber-500",
    };
  return {
    bg: "bg-red-50",
    text: "text-red-700",
    dot: "bg-red-500",
  };
}

// ── Source badge ──

const SOURCE_LABELS: Record<string, { label: string; className: string }> = {
  databricks: { label: "DB", className: "bg-orange-50 text-orange-700" },
  config_apis: { label: "CA", className: "bg-blue-50 text-blue-700" },
  capillary: { label: "CF", className: "bg-purple-50 text-purple-700" },
  manual: { label: "M", className: "bg-gray-50 text-gray-600" },
};

// ── TreeRow component ──

function TreeRow({
  node,
  depth,
}: {
  node: ContextTreeNode;
  depth: number;
}) {
  const { selectedNodeId, expandedNodes, selectNode, toggleExpand } =
    useContextEngineStore();

  const isSelected = selectedNodeId === node.id;
  const isExpanded = expandedNodes[node.id];
  const isLeaf = node.type === "leaf";
  const children = node.children || [];
  const secrets = node.secrets || [];
  const attachments = node.attachments || [];
  const secretRefs = node.secretRefs || [];
  const h = healthColors(node.health);
  const source = node.source ? SOURCE_LABELS[node.source] : null;

  return (
    <div>
      {/* Node row */}
      <div
        onClick={() => {
          selectNode(node.id);
          if (children.length > 0) toggleExpand(node.id);
        }}
        className={cn(
          "flex items-center gap-2 py-2 px-3.5 cursor-pointer transition-colors",
          "hover:bg-gray-50",
          isSelected && "bg-violet-50 border-l-[3px] border-violet-600",
          !isSelected && "border-l-[3px] border-transparent"
        )}
        style={{ paddingLeft: `${14 + depth * 22}px` }}
      >
        {/* Expand/collapse arrow */}
        {children.length > 0 ? (
          <span className="w-3 shrink-0 text-gray-400">
            {isExpanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
          </span>
        ) : (
          <span className="w-3 shrink-0" />
        )}

        {/* Node name */}
        <span
          className={cn(
            "flex-1 text-[13px] truncate",
            isLeaf ? "text-gray-700" : "font-semibold text-gray-900"
          )}
        >
          {node.name}
        </span>

        {/* Source badge */}
        {source && (
          <span
            className={cn(
              "rounded px-1.5 py-0.5 text-[10px] font-medium",
              source.className
            )}
          >
            {source.label}
          </span>
        )}

        {/* Visibility icon */}
        {node.visibility === "private" ? (
          <Lock className="h-3 w-3 text-gray-400 shrink-0" />
        ) : (
          <Globe className="h-3 w-3 text-gray-300 shrink-0" />
        )}

        {/* Health badge */}
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold",
            h.bg,
            h.text
          )}
        >
          <span className={cn("h-1.5 w-1.5 rounded-full", h.dot)} />
          {node.health}
        </span>

        {/* Attachment count */}
        {attachments.length > 0 && (
          <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] text-indigo-600">
            <Paperclip className="inline h-2.5 w-2.5 mr-0.5" />
            {attachments.length}
          </span>
        )}

        {/* Secret ref count */}
        {secretRefs.length > 0 && (
          <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700">
            <Key className="inline h-2.5 w-2.5 mr-0.5" />
            {secretRefs.length}
          </span>
        )}
      </div>

      {/* Secret rows (category-level) */}
      {isExpanded &&
        secrets.map((s) => (
          <div
            key={s.key}
            onClick={() => selectNode(`secret:${s.key}`)}
            className={cn(
              "flex items-center gap-2 py-1.5 px-3.5 cursor-pointer transition-colors",
              "hover:bg-amber-50/50",
              selectedNodeId === `secret:${s.key}`
                ? "bg-amber-50 border-l-[3px] border-amber-500"
                : "border-l-[3px] border-transparent"
            )}
            style={{ paddingLeft: `${14 + (depth + 1) * 22}px` }}
          >
            <span className="w-3 shrink-0" />
            <Key className="h-3.5 w-3.5 text-amber-600 shrink-0" />
            <span className="font-mono text-xs text-amber-800">{`{{${s.key}}}`}</span>
            <span className="ml-auto text-[10px] text-amber-600">{s.scope}</span>
          </div>
        ))}

      {/* Attachment rows (when selected) */}
      {isSelected &&
        attachments.map((a) => (
          <div
            key={a.name}
            className="flex items-center gap-2 py-1 px-3.5"
            style={{ paddingLeft: `${14 + (depth + 1) * 22}px` }}
          >
            <span className="w-3 shrink-0" />
            <FileText
              className={cn(
                "h-3.5 w-3.5 shrink-0",
                a.sensitive ? "text-red-500" : "text-indigo-500"
              )}
            />
            <span className="flex-1 text-xs text-gray-700 truncate">
              {a.name}
            </span>
            {a.sensitive && (
              <span className="rounded bg-red-50 px-1 py-0.5 text-[9px] text-red-600">
                sensitive
              </span>
            )}
            <span className="text-[10px] text-gray-400">{a.size}</span>
          </div>
        ))}

      {/* Children */}
      {isExpanded &&
        children.map((child) => (
          <TreeRow key={child.id} node={child} depth={depth + 1} />
        ))}
    </div>
  );
}

// ── Main TreeView ──

export function TreeView() {
  const { treeData, expandAll, collapseAll } = useContextEngineStore();

  if (!treeData) {
    return (
      <div className="flex items-center justify-center py-12 text-sm text-gray-400">
        No tree data. Generate a tree to get started.
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center justify-between border-b border-gray-200 px-4 py-2">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
          Context Tree
        </h3>
        <div className="flex items-center gap-2">
          <button
            onClick={expandAll}
            className="text-[11px] text-gray-500 hover:text-gray-700"
          >
            Expand All
          </button>
          <span className="text-gray-300">|</span>
          <button
            onClick={collapseAll}
            className="text-[11px] text-gray-500 hover:text-gray-700"
          >
            Collapse
          </button>
        </div>
      </div>

      {/* Tree */}
      <div className="flex-1 overflow-y-auto">
        <TreeRow node={treeData} depth={0} />
      </div>

      {/* Footer */}
      <TreeFooter tree={treeData} />
    </div>
  );
}

// ── Footer stats ──

function TreeFooter({ tree }: { tree: ContextTreeNode }) {
  const nodeCount = countNodes(tree);
  return (
    <div className="border-t border-gray-200 px-4 py-2 flex items-center justify-between text-[11px] text-gray-400">
      <span>{nodeCount} nodes</span>
      <span>
        Health:{" "}
        <span
          className={cn(
            "font-semibold",
            tree.health >= 80
              ? "text-green-600"
              : tree.health >= 60
                ? "text-amber-600"
                : "text-red-600"
          )}
        >
          {tree.health}%
        </span>
      </span>
    </div>
  );
}

function countNodes(node: ContextTreeNode): number {
  let count = 1;
  for (const child of node.children || []) {
    count += countNodes(child);
  }
  return count;
}
